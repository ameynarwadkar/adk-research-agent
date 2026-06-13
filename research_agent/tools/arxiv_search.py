"""ArXiv search tool — searches for academic papers on ArXiv.

Uses the ``arxiv`` Python library to query the ArXiv API.
This is a plain function that ADK wraps as a FunctionTool automatically.
"""

from __future__ import annotations

import logging

import arxiv

from research_agent.models.paper import Author, Paper

logger = logging.getLogger(__name__)


def _to_paper(result: arxiv.Result) -> Paper:
    """Convert an arxiv.Result into our shared Paper model."""
    authors = [Author(name=a.name) for a in result.authors]
    return Paper(
        paper_id=result.get_short_id(),
        title=result.title,
        authors=authors,
        abstract=result.summary.replace("\n", " "),
        year=result.published.year,
        citation_count=0,
        venue="arxiv",
        url=result.entry_id,
        fields_of_study=list(result.categories),
        is_open_access=True,
    )


def search_arxiv(query: str, max_results: int = 20) -> dict:
    """Search ArXiv for academic papers matching the query.

    Args:
        query: Free-text search query (e.g. 'graph neural networks drug discovery').
        max_results: Maximum number of results to return. Default 20, max 30.

    Returns:
        Dictionary with 'papers' list, 'query', 'total_results', and 'source' fields.
    """
    max_results = min(max_results, 30)
    logger.info("ArXiv search: '%s' (limit=%d)", query, max_results)

    try:
        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        papers = [_to_paper(result) for result in client.results(search)]
        logger.info("ArXiv search '%s': found %d papers", query, len(papers))

        return {
            "papers": [p.model_dump() for p in papers],
            "query": query,
            "total_results": len(papers),
            "source": "arxiv",
        }

    except Exception as exc:
        logger.error("ArXiv search failed: %s", exc)
        return {
            "papers": [],
            "query": query,
            "total_results": 0,
            "source": "arxiv",
            "error": f"ArXiv search failed: {exc}",
        }