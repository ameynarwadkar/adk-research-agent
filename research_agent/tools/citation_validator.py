"""Citation validator — verifies PMIDs/paper IDs against PubMed in real-time.

Extracts all PMID-like strings from text, batch-queries PubMed's esummary API,
and returns a report of which citations are real vs fabricated. Also checks
for title mismatches (real PMID but wrong paper).
"""

from __future__ import annotations

from langfuse.decorators import observe

import logging
import re

import httpx

logger = logging.getLogger(__name__)

_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


import os
from research_agent.retrylogic import retry
from research_agent.retrylogic.exceptions import RateLimitError, ExternalAPIError
from research_agent.retrylogic.breakers import pubmed_breaker
from research_agent.tools.cache import get_cached_response, set_cached_response

_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


@retry(
    max_attempts=3,
    base_delay=1.0,
    max_delay=10.0,
    retry_on=(RateLimitError, ExternalAPIError),
)
def _validate_citations_api(pmids: list[str]) -> dict:
    if not pmids:
        return {}

    api_key = os.getenv("PUBMED_API_KEY") or os.getenv("NCBI_API_KEY")
    headers = {
        "User-Agent": "ADK-ResearchAgent/0.1.0 (mailto:amey@example.com)",
    }

    with pubmed_breaker:
        with httpx.Client(timeout=25.0) as client:
            params = {
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "json",
            }
            if api_key:
                params["api_key"] = api_key

            try:
                resp = client.get(_ESUMMARY_URL, params=params, headers=headers)
            except httpx.RequestError as e:
                raise ExternalAPIError(f"Validation network error: {e}", service_name="PubMed")

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "5"))
                raise RateLimitError("PubMed validation rate limited", service_name="PubMed", retry_after=retry_after)
            elif resp.status_code >= 400:
                raise ExternalAPIError(
                    f"PubMed validation failed with status {resp.status_code}",
                    status_code=resp.status_code,
                    service_name="PubMed",
                )

            return resp.json()


@observe()
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
    logger.info("validate_citations tool called with text length %d characters", len(text))
    # Extract all PMIDs from text (handles PMID:123, PMID: 123, PMID 123)
    pmid_pattern = r"PMID[:\s]*(\d{6,10})"
    raw_pmids = re.findall(pmid_pattern, text, re.IGNORECASE)
    unique_pmids = sorted(set(raw_pmids))

    if not unique_pmids:
        logger.info("No PMIDs found in the text. Validation skipped.")
        return {
            "valid": [],
            "invalid": [],
            "total_checked": 0,
            "summary": "No PMIDs found in text to validate.",
        }

    logger.info("Found %d unique PMIDs to validate: %s", len(unique_pmids), unique_pmids)

    valid: list[dict] = []
    invalid: list[dict] = []
    pmids_to_fetch: list[str] = []

    # Check cache first for each PMID individually to minimize redundant calls
    for pmid in unique_pmids:
        cached = get_cached_response("pmid", pmid)
        if cached:
            status = cached.get("status")
            logger.info("PMID %s: Cache HIT (status: %s)", pmid, status)
            if status == "valid":
                valid.append(cached["data"])
            else:
                invalid.append(cached["data"])
        else:
            logger.info("PMID %s: Cache MISS. Will fetch from PubMed API.", pmid)
            pmids_to_fetch.append(pmid)

    # Fetch remaining PMIDs from API if any
    if pmids_to_fetch:
        logger.info("Requesting live validation for %d PMIDs from PubMed: %s", len(pmids_to_fetch), pmids_to_fetch)
        try:
            data = _validate_citations_api(pmids_to_fetch)
            results = data.get("result", {})

            for pmid in pmids_to_fetch:
                entry = results.get(pmid)
                if entry and "error" not in entry:
                    item = {
                        "pmid": pmid,
                        "actual_title": entry.get("title", "Unknown"),
                        "actual_source": entry.get("source", "Unknown"),
                        "actual_pubdate": entry.get("pubdate", "Unknown"),
                        "actual_authors": entry.get("sortfirstauthor", "Unknown"),
                    }
                    logger.info("PMID %s: VALID. Title: '%s'", pmid, item["actual_title"])
                    valid.append(item)
                    set_cached_response("pmid", pmid, {"status": "valid", "data": item})
                else:
                    reason = "Not found in PubMed"
                    if entry and "error" in entry:
                        reason = entry["error"]
                    logger.warning("PMID %s: INVALID. Reason: %s", pmid, reason)
                    item = {
                        "pmid": pmid,
                        "reason": reason,
                    }
                    invalid.append(item)
                    set_cached_response("pmid", pmid, {"status": "invalid", "data": item})

        except Exception as e:
            logger.error("Citation validation API call failed: %s", e)
            for pmid in pmids_to_fetch:
                logger.warning("PMID %s: Marked invalid due to API failure: %s", pmid, e)
                invalid.append({
                    "pmid": pmid,
                    "reason": f"Validation API error: {e}",
                })

    # Sort to maintain consistent output order
    valid.sort(key=lambda x: x["pmid"])
    invalid.sort(key=lambda x: x["pmid"])

    # Build human-readable summary
    summary_parts = [f"Checked {len(unique_pmids)} unique PMIDs against PubMed."]
    if valid:
        summary_parts.append(f"{len(valid)} exist in PubMed.")
    if invalid:
        bad_ids = ", ".join(i["pmid"] for i in invalid if "API error" not in i["reason"])
        if bad_ids:
            summary_parts.append(f"{len([i for i in invalid if 'API error' not in i['reason']])} INVALID or NOT FOUND: [{bad_ids}].")
        failed_count = len([i for i in invalid if "API error" in i["reason"]])
        if failed_count:
            summary_parts.append(f"{failed_count} failed verification due to API issues.")

    summary_parts.append(
        "IMPORTANT: Even 'valid' PMIDs may be MISMATCHED — check that each "
        "actual_title matches the topic it's cited for in the review."
    )

    final_summary = " ".join(summary_parts)
    logger.info("Validation complete. Summary: %s", final_summary)

    return {
        "valid": valid,
        "invalid": invalid,
        "total_checked": len(unique_pmids),
        "summary": final_summary,
    }
