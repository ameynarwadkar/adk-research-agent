"""Citation traversal — forward/backward citation graph via Semantic Scholar.

Uses the Semantic Scholar API to traverse citations. Synchronous client
since ADK runs tool functions in a thread pool.
"""

import logging
import time
from typing import Any

import httpx

from research_agent.models.paper import Author, Paper

logger = logging.getLogger(__name__)

_S2_BASE_URL = "https://api.semanticscholar.org/graph/v1"
_PAPER_FIELDS = "paperId,title,abstract,year,citationCount,venue,url,authors,tldr,fieldsOfStudy,isOpenAccess"


def _parse_s2_paper(data: dict[str, Any]) -> Paper | None:
    """Convert a Semantic Scholar API paper dict to our Paper model."""
    if not data or not data.get("paperId"):
        return None

    authors = [
        Author(
            name=a.get("name", "Unknown"),
            author_id=a.get("authorId"),
        )
        for a in data.get("authors", [])
    ]

    tldr_data = data.get("tldr")
    tldr = tldr_data.get("text") if isinstance(tldr_data, dict) else None

    return Paper(
        paper_id=data.get("paperId", ""),
        title=data.get("title", "Untitled"),
        authors=authors,
        abstract=data.get("abstract"),
        year=data.get("year"),
        citation_count=data.get("citationCount", 0),
        venue=data.get("venue") or None,
        url=data.get("url", f"https://www.semanticscholar.org/paper/{data.get('paperId', '')}"),
        tldr=tldr,
        fields_of_study=data.get("fieldsOfStudy") or [],
        is_open_access=data.get("isOpenAccess", False),
    )


from research_agent.retrylogic import retry
from research_agent.retrylogic.exceptions import RateLimitError, ExternalAPIError
from research_agent.retrylogic.breakers import s2_breaker
from research_agent.tools.cache import get_cached_response, set_cached_response


@retry(
    max_attempts=3,
    base_delay=1.2,
    max_delay=10.0,
    retry_on=(RateLimitError, ExternalAPIError),
)
def _fetch_citations_api(
    client: httpx.Client,
    paper_id: str,
    endpoint: str,
) -> list[Paper]:
    headers = {
        "User-Agent": "ADK-ResearchAgent/0.1.0 (mailto:amey@example.com)",
    }

    # Rate limiting: S2 unauthenticated ~1 req/sec
    time.sleep(1.2)

    with s2_breaker:
        try:
            response = client.get(
                f"{_S2_BASE_URL}/paper/{paper_id}/{endpoint}",
                params={"fields": _PAPER_FIELDS, "limit": 20},
                headers=headers,
            )
        except httpx.RequestError as e:
            raise ExternalAPIError(f"Semantic Scholar network error: {e}", service_name="SemanticScholar")

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "5"))
            raise RateLimitError("Semantic Scholar rate limited", service_name="SemanticScholar", retry_after=retry_after)
        elif response.status_code >= 400:
            raise ExternalAPIError(
                f"Semantic Scholar API failed with status {response.status_code}",
                status_code=response.status_code,
                service_name="SemanticScholar",
            )

        data = response.json()
        key = "citingPaper" if endpoint == "citations" else "citedPaper"
        papers: list[Paper] = []
        for item in data.get("data", []):
            paper = _parse_s2_paper(item.get(key, {}))
            if paper is not None:
                papers.append(paper)

        return papers


def _fetch_citations(
    client: httpx.Client,
    paper_id: str,
    endpoint: str,  # "citations" or "references"
) -> list[Paper]:
    """Fetch forward citations or backward references for a paper (cached wrapper)."""
    cache_key = f"paper:{paper_id}|endpoint:{endpoint}"
    cached = get_cached_response("semanticscholar", cache_key)
    if cached:
        return [Paper.model_validate(p) for p in cached["papers"]]

    try:
        papers = _fetch_citations_api(client, paper_id, endpoint)
        set_cached_response(
            "semanticscholar",
            cache_key,
            {"papers": [p.model_dump() for p in papers]}
        )
        return papers
    except Exception as e:
        logger.warning("Failed to fetch %s for %s: %s", endpoint, paper_id, e)
        return []


@observe()
def traverse_citations(
    paper_id: str,
    direction: str = "both",
    depth: int = 1,
) -> dict:
    """Traverse the citation graph of a paper using Semantic Scholar.

    Direction 'forward' returns papers that cite this paper,
    'backward' returns papers referenced by this paper,
    'both' returns the union. Useful for snowball discovery of related work.

    Args:
        paper_id: Paper identifier — can be a Semantic Scholar ID, DOI,
                  ArXiv ID (prefix with 'ARXIV:'), or PMID (prefix with 'PMID:').
        direction: 'forward', 'backward', or 'both'. Default 'both'.
        depth: How many hops to traverse. Default 1, max 2.

    Returns:
        Dictionary with 'papers' list, 'count', and traversal metadata.
    """
    depth = min(depth, 2)
    all_papers: dict[str, Paper] = {}
    papers_to_process = [paper_id]

    try:
        with httpx.Client(timeout=30.0) as client:
            for current_depth in range(depth):
                next_batch: list[str] = []

                for pid in papers_to_process:
                    forward_papers: list[Paper] = []
                    backward_papers: list[Paper] = []

                    if direction in ("forward", "both"):
                        forward_papers = _fetch_citations(client, pid, "citations")

                    if direction in ("backward", "both"):
                        backward_papers = _fetch_citations(client, pid, "references")

                    for p in forward_papers + backward_papers:
                        if p.paper_id not in all_papers:
                            all_papers[p.paper_id] = p
                            if current_depth + 1 < depth:
                                next_batch.append(p.paper_id)

                papers_to_process = next_batch[:10]  # Cap to avoid explosion

        result_papers = list(all_papers.values())

        logger.info(
            "Citation traversal for '%s' (direction=%s, depth=%d): found %d papers",
            paper_id, direction, depth, len(result_papers),
        )

        return {
            "papers": [p.model_dump() for p in result_papers],
            "count": len(result_papers),
            "source_paper_id": paper_id,
            "direction": direction,
            "depth": depth,
        }

    except httpx.HTTPError as e:
        logger.warning("Semantic Scholar API unavailable: %s", e)
        return {
            "papers": [],
            "count": 0,
            "source_paper_id": paper_id,
            "error": f"Semantic Scholar unavailable: {e}",
        }
    except Exception as e:
        logger.warning("Citation traversal failed: %s", e)
        return {
            "papers": [],
            "count": 0,
            "source_paper_id": paper_id,
            "error": f"Citation traversal failed: {e}",
        }