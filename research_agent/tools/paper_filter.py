"""Paper filtering — filter papers by year, citations, keywords, etc."""

import json
import logging

from research_agent.models.paper import Paper

logger = logging.getLogger(__name__)


def filter_papers(
    papers: list[dict],
    min_year: int | None = None,
    max_year: int | None = None,
    min_citations: int | None = None,
    keywords: list[str] | None = None,
    open_access_only: bool = False,
) -> dict:
    """Filter a list of papers by various criteria.

    Returns only papers matching ALL specified criteria. Pass the papers list
    from a previous search_arxiv or search_pubmed call.

    Args:
        papers: List of paper objects (dicts) to filter.
        min_year: Include only papers from this year onward. Optional.
        max_year: Include only papers up to this year. Optional.
        min_citations: Minimum citation count. Optional.
        keywords: Papers must contain ALL of these keywords in title or abstract. Case-insensitive. Optional.
        open_access_only: If true, only include open-access papers. Default false.

    Returns:
        Dictionary with filtered 'papers' list, 'count', and 'filters_applied'.
    """
    if not papers:
        return {"papers": [], "count": 0, "filters_applied": []}

    parsed = []
    for p in papers:
        try:
            parsed.append(Paper.model_validate(p))
        except Exception:
            logger.warning("Skipping invalid paper dict in filter_papers")
    original_count = len(parsed)
    filters_applied: list[str] = []

    # Year filter
    if min_year is not None:
        parsed = [p for p in parsed if p.year is not None and p.year >= min_year]
        filters_applied.append(f"year >= {min_year}")
    if max_year is not None:
        parsed = [p for p in parsed if p.year is not None and p.year <= max_year]
        filters_applied.append(f"year <= {max_year}")

    # Citation filter
    if min_citations is not None:
        parsed = [p for p in parsed if p.citation_count >= min_citations]
        filters_applied.append(f"citations >= {min_citations}")

    # Keyword filter
    if keywords:
        lower_keywords = [k.lower() for k in keywords]

        def matches(paper: Paper) -> bool:
            searchable = (paper.title + " " + (paper.abstract or "")).lower()
            return all(kw in searchable for kw in lower_keywords)

        parsed = [p for p in parsed if matches(p)]
        filters_applied.append(f"keywords: {', '.join(keywords)}")

    # Open access filter
    if open_access_only:
        parsed = [p for p in parsed if p.is_open_access]
        filters_applied.append("open access only")

    logger.info("Filtered papers: %d → %d (filters: %s)", original_count, len(parsed), filters_applied)

    return {
        "papers": [p.model_dump() for p in parsed],
        "count": len(parsed),
        "original_count": original_count,
        "filters_applied": filters_applied,
    }

