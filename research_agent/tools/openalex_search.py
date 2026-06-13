"""OpenAlex search tool — searches the OpenAlex open scholarly index.

OpenAlex indexes 250M+ scholarly works across all disciplines.
No API key required; add OPENALEX_EMAIL to .env for polite-pool
access (higher rate limits).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from research_agent.models.paper import Author, Paper

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
    max_results = min(max_results, 50)
    logger.info("OpenAlex search: '%s' (limit=%d)", query, max_results)

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

    # Polite pool: add email if configured
    email = os.getenv("OPENALEX_EMAIL")
    if email:
        params["mailto"] = email

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(_BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        papers = [p for r in results if (p := _parse_work(r)) is not None]
        total = data.get("meta", {}).get("count", len(papers))

        logger.info("OpenAlex search '%s': found %d papers (total=%d)", query, len(papers), total)

        return {
            "papers": [p.model_dump() for p in papers],
            "query": query,
            "total_results": total,
            "source": "openalex",
        }

    except httpx.HTTPError as exc:
        logger.warning("OpenAlex API unavailable: %s", exc)
        return {
            "papers": [],
            "query": query,
            "total_results": 0,
            "source": "openalex",
            "error": f"OpenAlex API unavailable: {exc}",
        }
    except Exception as exc:
        logger.warning("OpenAlex search failed: %s", exc)
        return {
            "papers": [],
            "query": query,
            "total_results": 0,
            "source": "openalex",
            "error": f"OpenAlex search failed: {exc}",
        }
