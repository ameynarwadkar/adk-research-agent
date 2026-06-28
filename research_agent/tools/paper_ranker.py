"""Paper ranking - sort and rank papers by citation count, year, etc."""

import logging
from research_agent.models.paper import Paper

logger = logging.getLogger(__name__)

@observe()
def rank_papers(
    papers: list[dict],
    sort_by: str = "citations",
    ascending: bool = False,
    top_n: int | None = None,
) -> dict:
    """Sort and rank a list of papers by citation count, year, or title.

    Use this to prioritize which papers to analyze in depth.

    Args:
        papers: List of paper objects (dicts) to rank.
        sort_by: Sort criterion. One of 'citations', 'year', 'title'. Default 'citations'.
        ascending: Sort in ascending order. Default false (descending).
        top_n: Return only the top N papers. Optional — returns all if not set.

    Returns:
        Dictionary with ranked 'papers' list, 'count', and 'sorted_by'.
    """
    if not papers:
        logger.info("Rank papers called with empty list.")
        return {"papers": [], "count": 0, "sorted_by": sort_by}

    parsed = [Paper.model_validate(p) for p in papers]
    logger.info("Ranking %d papers by attribute '%s' (ascending=%s, top_n=%s)", len(parsed), sort_by, ascending, top_n)

    sort_key_map = {
        "citations": lambda p: p.citation_count,
        "year": lambda p: p.year or 0,
        "title": lambda p: p.title.lower(),
    }

    key_func = sort_key_map.get(sort_by, sort_key_map["citations"])
    parsed.sort(key=key_func, reverse=not ascending)

    if top_n is not None:
        before = len(parsed)
        parsed = parsed[:top_n]
        logger.info("Capped ranked list to top_n=%d (was %d)", top_n, before)

    logger.info("Successfully ranked papers. Top paper ID: %s, Title: %s", parsed[0].paper_id if parsed else "None", parsed[0].title if parsed else "None")

    return {
        "papers": [p.model_dump() for p in parsed],
        "count": len(parsed),
        "sorted_by": sort_by,
        "ascending": ascending,
    }