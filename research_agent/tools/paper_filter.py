"""Paper filtering — filter papers by year, citations, keywords, etc."""

import json
import logging

from research_agent.models.paper import Paper

logger = logging.getLogger(__name__)


@observe()
def filter_papers(
    papers: list[dict],
    min_year: int | None = None,
    max_year: int | None = None,
    min_citations: int | None = None,
    keywords: list[str] | None = None,
    open_access_only: bool = False,
    exclude_protocols: bool = True,
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
        exclude_protocols: If true, exclude protocol/design papers and planned trials that have no results yet. Default true.

    Returns:
        Dictionary with filtered 'papers' list, 'count', and 'filters_applied'.
    """
    if not papers:
        logger.info("Filter papers called with an empty list.")
        return {"papers": [], "count": 0, "filters_applied": []}

    parsed = [Paper.model_validate(p) for p in papers]
    original_count = len(parsed)
    logger.info("Filtering started: %d initial paper candidates.", original_count)
    filters_applied: list[str] = []

    # Year filter
    if min_year is not None:
        before = len(parsed)
        parsed = [p for p in parsed if p.year is not None and p.year >= min_year]
        logger.info("Filter 'min_year >= %d': %d -> %d papers remaining.", min_year, before, len(parsed))
        filters_applied.append(f"year >= {min_year}")
    if max_year is not None:
        before = len(parsed)
        parsed = [p for p in parsed if p.year is not None and p.year <= max_year]
        logger.info("Filter 'max_year <= %d': %d -> %d papers remaining.", max_year, before, len(parsed))
        filters_applied.append(f"year <= {max_year}")

    # Citation filter
    if min_citations is not None:
        before = len(parsed)
        parsed = [p for p in parsed if p.citation_count >= min_citations]
        logger.info("Filter 'min_citations >= %d': %d -> %d papers remaining.", min_citations, before, len(parsed))
        filters_applied.append(f"citations >= {min_citations}")

    # Keyword filter
    if keywords:
        lower_keywords = [k.lower() for k in keywords]
        before = len(parsed)

        def matches(paper: Paper) -> bool:
            searchable = (paper.title + " " + (paper.abstract or "")).lower()
            return all(kw in searchable for kw in lower_keywords)

        parsed = [p for p in parsed if matches(p)]
        logger.info("Filter 'keywords %s': %d -> %d papers remaining.", keywords, before, len(parsed))
        filters_applied.append(f"keywords: {', '.join(keywords)}")

    # Open access filter
    if open_access_only:
        before = len(parsed)
        parsed = [p for p in parsed if p.is_open_access]
        logger.info("Filter 'open_access_only': %d -> %d papers remaining.", before, len(parsed))
        filters_applied.append("open access only")

    # Exclude protocol papers and planned trials
    if exclude_protocols:
        before = len(parsed)
        protocol_keywords = [
            "protocol",
            "planned trial",
            "design and rationale",
            "trial design",
            "recruiting",
            "study design for",
            "methodology and design",
        ]

        def is_protocol(paper: Paper) -> bool:
            searchable = (paper.title + " " + (paper.abstract or "")).lower()
            return any(pw in searchable for pw in protocol_keywords)

        parsed = [p for p in parsed if not is_protocol(p)]
        logger.info("Filter 'exclude_protocols': %d -> %d papers remaining.", before, len(parsed))
        filters_applied.append("exclude protocols")

    logger.info(
        "Filtering complete: kept %d of %d original papers (filters: %s)",
        len(parsed), original_count, filters_applied
    )

    return {
        "papers": [p.model_dump() for p in parsed],
        "count": len(parsed),
        "original_count": original_count,
        "filters_applied": filters_applied,
    }

