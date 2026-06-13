"""Abstract extraction — batch-process paper abstracts for analysis."""

import logging

from research_agent.models.paper import Paper

logger = logging.getLogger(__name__)


def extract_abstracts(
    papers: list[dict],
    include_metadata: bool = True,
) -> dict:
    """Extract abstracts from a list of papers and produce a structured digest.

    Papers without abstracts are flagged but included with their title.
    Use this to prepare papers for thematic analysis.

    Args:
        papers: List of paper objects (dicts) to extract abstracts from.
        include_metadata: Include citation count, year, venue alongside abstracts. Default true.

    Returns:
        Dictionary with 'digests' list and counts of papers with/without abstracts.
    """
    if not papers:
        return {"digests": [], "total_papers": 0, "with_abstract": 0, "without_text": 0}

    parsed = [Paper.model_validate(p) for p in papers]

    digests: list[dict] = []
    with_abstract = 0
    with_tldr = 0
    without_text = 0

    for paper in parsed:
        digest: dict = {
            "paper_id": paper.paper_id,
            "title": paper.title,
            "authors": paper.authors_str,
        }

        if paper.abstract:
            digest["text"] = paper.abstract
            digest["text_source"] = "abstract"
            with_abstract += 1
        elif paper.tldr:
            digest["text"] = paper.tldr
            digest["text_source"] = "tldr"
            with_tldr += 1
        else:
            digest["text"] = f"[No abstract available for: {paper.title}]"
            digest["text_source"] = "none"
            without_text += 1

        if include_metadata:
            digest["year"] = paper.year
            digest["citation_count"] = paper.citation_count
            digest["venue"] = paper.venue
            digest["fields_of_study"] = paper.fields_of_study

        digests.append(digest)

    logger.info(
        "Extracted abstracts: %d with abstract, %d with TLDR, %d without text",
        with_abstract, with_tldr, without_text,
    )

    return {
        "digests": digests,
        "total_papers": len(parsed),
        "with_abstract": with_abstract,
        "with_tldr_only": with_tldr,
        "without_text": without_text,
    }