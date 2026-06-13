"""PubMEd Search tool - searches for academic papers on PubMed.

Uses esearch (find PMIDs) and efetch (get records) from NCBI API.
"""

from __future__ import annotations

import logging
from typing import Any
from xml.etree import ElementTree

import httpx
from research_agent.models.paper import Author, Paper

logger = logging.getLogger(__name__)

_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def _parse_pubmed_xml(xml_text: str) -> list[Paper]:
    """Parse PubMed XML into list of Paper objects.

    This is a simplified parser. For production, use Biopython's Entrez.
    """
    papers: list[Paper] = []
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        logger.warning("Failed to parse PubMed XML response")
        return papers

    for article in root.findall(".//PubmedArticle"):
        try:
            medline = article.find("MedlineCitation")
            if medline is None:
                continue
            pmid_elem = medline.find("PMID")
            pmid = pmid_elem.text if pmid_elem is not None else ""

            article_data = medline.find("Article")
            if article_data is None:
                continue

            # Title
            title_elem = article_data.find("ArticleTitle")
            title = title_elem.text if title_elem is not None else "Untitled"

            # Abstract
            abstract_elem = article_data.find(".//AbstractText")
            abstract = abstract_elem.text if abstract_elem is not None else None

            # Authors
            authors: list[Author] = []
            author_list = article_data.find("AuthorList")
            if author_list is not None:
                for author_elem in author_list.findall("Author"):
                    last = author_elem.find("LastName")
                    fore = author_elem.find("ForeName")
                    if last is not None and last.text:
                        name = last.text
                        if fore is not None and fore.text:
                            name = f"{fore.text} {last.text}"
                        authors.append(Author(name=name))

            # Year
            year: int | None = None
            for date_xpath in (".//PubDate", ".//ArticleDate"):
                date_elem = article_data.find(date_xpath)
                if date_elem is not None:
                    year_elem = date_elem.find("Year")
                    if year_elem is not None and year_elem.text:
                        try:
                            year = int(year_elem.text)
                            break
                        except ValueError:
                            pass

            # Journal
            journal_elem = article_data.find(".//Journal/Title")
            venue = journal_elem.text if journal_elem is not None else None

            papers.append(Paper(
                paper_id=f"PMID:{pmid}",
                title=title or "Untitled",
                authors=authors,
                abstract=abstract,
                year=year,
                citation_count=0,
                venue=venue,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                fields_of_study=["Medicine"],
                is_open_access=False,
            ))
        except Exception:
            logger.warning("Failed to parse PubMed article, skipping", exc_info=True)
            continue

    return papers


def search_pubmed(query: str, max_results: int = 20, date_from: str | None = None) -> dict:
    """Search PubMed for biomedical and life sciences papers.

    Uses NCBI E-utilities to find papers matching the query. Best for medical,
    biological, and clinical research topics.

    Args:
        query: Search query (e.g. 'CRISPR gene therapy clinical trials').
        max_results: Maximum number of papers to return. Default 20, max 50.
        date_from: Earliest publication date in YYYY/MM/DD or YYYY format. Optional.

    Returns:
        Dictionary with 'papers' list, 'query', 'total_results', and 'source' fields.
    """
    max_results = min(max_results, 50)

    try:
        with httpx.Client(timeout=30.0) as client:
            # Step 1: esearch to get PMIDs
            esearch_params: dict[str, Any] = {
                "db": "pubmed",
                "term": query,
                "retmax": max_results,
                "retmode": "json",
                "sort": "relevance",
            }
            if date_from:
                esearch_params["mindate"] = date_from
                esearch_params["datetype"] = "pdat"

            esearch_resp = client.get(_ESEARCH_URL, params=esearch_params)
            esearch_resp.raise_for_status()
            esearch_data = esearch_resp.json()

            id_list = esearch_data.get("esearchresult", {}).get("idlist", [])
            if not id_list:
                return {
                    "papers": [],
                    "query": query,
                    "total_results": 0,
                    "source": "pubmed",
                }

            # Step 2: efetch to get full article data
            efetch_params = {
                "db": "pubmed",
                "id": ",".join(id_list),
                "retmode": "xml",
                "rettype": "abstract",
            }
            efetch_resp = client.get(_EFETCH_URL, params=efetch_params)
            efetch_resp.raise_for_status()

            papers = _parse_pubmed_xml(efetch_resp.text)

            logger.info("PubMed search '%s': found %d papers", query, len(papers))

            return {
                "papers": [p.model_dump() for p in papers],
                "query": query,
                "total_results": int(
                    esearch_data.get("esearchresult", {}).get("count", len(papers))
                ),
                "source": "pubmed",
            }

    except httpx.HTTPError as e:
        logger.warning("PubMed API unavailable: %s", e)
        return {
            "papers": [],
            "query": query,
            "total_results": 0,
            "source": "pubmed",
            "error": f"PubMed API unavailable: {e}",
        }
    except Exception as e:
        logger.warning("PubMed search failed: %s", e)
        return {
            "papers": [],
            "query": query,
            "total_results": 0,
            "source": "pubmed",
            "error": f"PubMed search failed: {e}",
        }