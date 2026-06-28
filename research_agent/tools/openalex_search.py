import logging
import os
from typing import Any

import httpx

from research_agent.models.paper import Author, Paper
from research_agent.retrylogic import retry
from research_agent.retrylogic.exceptions import RateLimitError, ExternalAPIError
from research_agent.retrylogic.breakers import openalex_breaker
from research_agent.tools.cache import get_cached_response, set_cached_response

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.openalex.org/works"
_FIELDS = (
    "id,doi,title,authorships,publication_year,cited_by_count,"
    "primary_location,open_access,abstract_inverted_index,"
    "concepts,best_oa_url"
)


def _reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """Reconstruct a plain-text abstract from OpenAlex's inverted index format.

    OpenAlex stores abstracts as {word: [position, ...]} dicts to save space.
    This rebuilds the original word order.
    """
    if not inverted_index:
        return None
    words: dict[int, str] = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            words[pos] = word
    if not words:
        return None
    return " ".join(words[i] for i in sorted(words))


def _parse_work(work: dict[str, Any]) -> Paper | None:
    """Convert an OpenAlex work dict into our Paper model."""
    work_id = work.get("id", "")
    if not work_id:
        return None

    # Use short OpenAlex ID (e.g. W2741809807) as paper_id
    short_id = work_id.replace("https://openalex.org/", "")

    authors = [
        Author(name=a["author"]["display_name"])
        for a in work.get("authorships", [])
        if a.get("author") and a["author"].get("display_name")
    ]

    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))

    # Venue: prefer journal name from primary_location
    venue: str | None = None
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    venue = source.get("display_name") or None

    # Open access URL
    oa_info = work.get("open_access") or {}
    is_oa = oa_info.get("is_oa", False)
    url = (
        work.get("best_oa_url")
        or work.get("doi")
        or f"https://openalex.org/{short_id}"
    )

    # Fields of study from concepts (top 5 by score)
    concepts = sorted(
        work.get("concepts") or [],
        key=lambda c: c.get("score", 0),
        reverse=True,
    )
    fields_of_study = [c["display_name"] for c in concepts[:5] if c.get("display_name")]

    try:
        return Paper(
            paper_id=short_id,
            title=work.get("title") or "Untitled",
            authors=authors,
            abstract=abstract,
            year=work.get("publication_year"),
            citation_count=work.get("cited_by_count", 0),
            venue=venue,
            url=url,
            fields_of_study=fields_of_study,
            is_open_access=is_oa,
        )
    except Exception as exc:
        logger.warning("Failed to parse OpenAlex work %s: %s", short_id, exc)
        return None


@retry(
    max_attempts=3,
    base_delay=1.0,
    max_delay=10.0,
    retry_on=(RateLimitError, ExternalAPIError),
)
def _search_openalex_api(
    query: str,
    max_results: int = 20,
    from_year: int | None = None,
    to_year: int | None = None,
) -> dict:
    max_results = min(max_results, 50)
    logger.info("Executing live OpenAlex API search. Query: '%s' | Limit: %d", query, max_results)

    params: dict[str, Any] = {
        "search": query,
        "per-page": max_results,
        "sort": "relevance_score:desc",
        "select": _FIELDS,
    }

    # Year filter — OpenAlex uses filter param
    year_filters: list[str] = []
    if from_year:
        year_filters.append(f"publication_year:>{from_year - 1}")
    if to_year:
        year_filters.append(f"publication_year:<{to_year + 1}")
    if year_filters:
        params["filter"] = ",".join(year_filters)
        logger.info("Adding year filters to OpenAlex request: %s", params["filter"])

    # Polite pool: add email if configured
    email = os.getenv("OPENALEX_EMAIL")
    if email:
        params["mailto"] = email
        logger.info("Using polite pool mailto: %s", email)

    headers = {
        "User-Agent": "ADK-ResearchAgent/0.1.0 (mailto:amey@example.com)",
    }

    with openalex_breaker:
        with httpx.Client(timeout=30.0) as client:
            logger.info("Sending GET request to OpenAlex endpoint: %s with params %s", _BASE_URL, params)
            try:
                resp = client.get(_BASE_URL, params=params, headers=headers)
            except httpx.RequestError as exc:
                logger.error("OpenAlex GET request failed: %s", exc)
                raise ExternalAPIError(f"OpenAlex network error: {exc}", service_name="OpenAlex")

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "5"))
                logger.warning("OpenAlex hit 429 rate limit. Retry-After: %d", retry_after)
                raise RateLimitError("OpenAlex API rate limited", service_name="OpenAlex", retry_after=retry_after)
            elif resp.status_code >= 400:
                logger.error("OpenAlex failed with status code %d", resp.status_code)
                raise ExternalAPIError(
                    f"OpenAlex API failed with status {resp.status_code}",
                    status_code=resp.status_code,
                    service_name="OpenAlex",
                )

            data = resp.json()

        results = data.get("results", [])
        logger.info("Received %d raw works from OpenAlex.", len(results))
        papers = [p for r in results if (p := _parse_work(r)) is not None]
        total = data.get("meta", {}).get("count", len(papers))

        logger.info("OpenAlex parsed results: successfully mapped %d out of %d works (total hits=%d)", len(papers), len(results), total)

        return {
            "papers": [p.model_dump() for p in papers],
            "query": query,
            "total_results": total,
            "source": "openalex",
        }


@observe()
def search_openalex(
    query: str,
    max_results: int = 20,
    from_year: int | None = None,
    to_year: int | None = None,
) -> dict:
    """Search OpenAlex for scholarly works matching the query.

    OpenAlex indexes 250M+ works across all disciplines — preprints,
    journal articles, books, datasets, and more. No API key required.

    Args:
        query: Free-text search query (e.g. 'intermittent fasting type 2 diabetes RCT').
        max_results: Maximum number of results to return. Default 20, max 50.
        from_year: Filter to works published from this year onward. Optional.
        to_year: Filter to works published up to this year. Optional.

    Returns:
        Dictionary with 'papers' list, 'query', 'total_results', and 'source' fields.
    """
    logger.info("search_openalex tool entry. Query: '%s' | Limit: %d | Years: %s-%s", query, max_results, from_year, to_year)

    # Use local cache to prevent redundant API calls
    cache_key = f"query:{query}|limit:{max_results}|from:{from_year}|to:{to_year}"
    cached = get_cached_response("openalex", cache_key)
    if cached:
        logger.info("OpenAlex search cache hit for key: %s", cache_key[:40])
        return cached

    logger.info("OpenAlex cache miss. Triggering live search.")
    try:
        res = _search_openalex_api(query, max_results, from_year, to_year)
        set_cached_response("openalex", cache_key, res)
        return res
    except Exception as e:
        logger.warning("OpenAlex search failed: %s", e)
        return {
            "papers": [],
            "query": query,
            "total_results": 0,
            "source": "openalex",
            "error": f"OpenAlex search failed: {e}",
        }
