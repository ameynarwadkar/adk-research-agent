"""Citation validator — verifies PMIDs/paper IDs against PubMed in real-time.

Extracts all PMID-like strings from text, batch-queries PubMed's esummary API,
and returns a report of which citations are real vs fabricated. Also checks
for title mismatches (real PMID but wrong paper).
"""

from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)

_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


def validate_citations(text: str) -> dict:
    """Validate all PMIDs found in a text against PubMed's database.

    Extracts any PMID-like strings (PMID:XXXXX, PMID: XXXXX, PMID XXXXX),
    queries PubMed's esummary API to verify they exist, and returns the
    actual titles so the caller can check for topic mismatches.

    Args:
        text: The text containing PMID citations to validate.

    Returns:
        Dictionary with 'valid', 'invalid', 'total_checked', and 'summary'.
        Each valid entry includes the actual_title from PubMed for mismatch checking.
    """
    # Extract all PMIDs from text (handles PMID:123, PMID: 123, PMID 123)
    pmid_pattern = r"PMID[:\s]*(\d{6,10})"
    raw_pmids = re.findall(pmid_pattern, text, re.IGNORECASE)
    unique_pmids = sorted(set(raw_pmids))

    if not unique_pmids:
        return {
            "valid": [],
            "invalid": [],
            "total_checked": 0,
            "summary": "No PMIDs found in text to validate.",
        }

    logger.info("Validating %d unique PMIDs against PubMed", len(unique_pmids))

    valid: list[dict] = []
    invalid: list[dict] = []

    try:
        with httpx.Client(timeout=25.0) as client:
            # Batch query PubMed esummary (handles up to ~200 IDs per request)
            resp = client.get(
                _ESUMMARY_URL,
                params={
                    "db": "pubmed",
                    "id": ",".join(unique_pmids),
                    "retmode": "json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("result", {})

            for pmid in unique_pmids:
                entry = results.get(pmid)
                if entry and "error" not in entry:
                    valid.append({
                        "pmid": pmid,
                        "actual_title": entry.get("title", "Unknown"),
                        "actual_source": entry.get("source", "Unknown"),
                        "actual_pubdate": entry.get("pubdate", "Unknown"),
                        "actual_authors": entry.get("sortfirstauthor", "Unknown"),
                    })
                else:
                    reason = "Not found in PubMed"
                    if entry and "error" in entry:
                        reason = entry["error"]
                    invalid.append({
                        "pmid": pmid,
                        "reason": reason,
                    })

    except httpx.HTTPError as e:
        logger.error("PubMed esummary API error: %s", e)
        # If API fails, mark all as unverified rather than silently passing
        for pmid in unique_pmids:
            invalid.append({
                "pmid": pmid,
                "reason": f"Verification API unavailable: {e}",
            })
    except Exception as e:
        logger.error("Citation validation failed: %s", e)
        for pmid in unique_pmids:
            invalid.append({
                "pmid": pmid,
                "reason": f"Validation error: {e}",
            })

    # Build human-readable summary
    summary_parts = [f"Checked {len(unique_pmids)} unique PMIDs against PubMed."]
    if valid:
        summary_parts.append(f"{len(valid)} exist in PubMed.")
    if invalid:
        bad_ids = ", ".join(i["pmid"] for i in invalid)
        summary_parts.append(f"{len(invalid)} INVALID or NOT FOUND: [{bad_ids}].")
    summary_parts.append(
        "IMPORTANT: Even 'valid' PMIDs may be MISMATCHED — check that each "
        "actual_title matches the topic it's cited for in the review."
    )

    return {
        "valid": valid,
        "invalid": invalid,
        "total_checked": len(unique_pmids),
        "summary": " ".join(summary_parts),
    }
