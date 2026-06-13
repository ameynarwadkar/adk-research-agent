"""Tests for filter_papers, rank_papers, and extract_abstracts tools.

All three are pure functions (no HTTP) — no mocking needed.
"""

import pytest

from research_agent.tools.paper_filter import filter_papers
from research_agent.tools.paper_ranker import rank_papers
from research_agent.tools.abstract_extractor import extract_abstracts


# ── filter_papers ─────────────────────────────────────────────────────────

class TestFilterPapers:
    def test_empty_input(self):
        result = filter_papers([])
        assert result["papers"] == []
        assert result["count"] == 0

    def test_no_filters_returns_all(self, paper_dicts):
        result = filter_papers(paper_dicts)
        assert result["count"] == len(paper_dicts)

    def test_min_year_filter(self, paper_dicts):
        # paper_list years: 2024, 2022, 2018
        result = filter_papers(paper_dicts, min_year=2022)
        years = [p["year"] for p in result["papers"]]
        assert all(y >= 2022 for y in years)
        assert "year >= 2022" in result["filters_applied"]

    def test_max_year_filter(self, paper_dicts):
        result = filter_papers(paper_dicts, max_year=2022)
        years = [p["year"] for p in result["papers"] if p["year"] is not None]
        assert all(y <= 2022 for y in years)

    def test_year_range_filter(self, paper_dicts):
        result = filter_papers(paper_dicts, min_year=2022, max_year=2023)
        assert result["count"] == 1
        assert result["papers"][0]["year"] == 2022

    def test_min_citations_filter(self, paper_dicts):
        # citations: 42, 105, 0
        result = filter_papers(paper_dicts, min_citations=50)
        assert result["count"] == 1
        assert result["papers"][0]["citation_count"] == 105

    def test_keyword_filter_case_insensitive(self, paper_dicts):
        result = filter_papers(paper_dicts, keywords=["INTERMITTENT", "fasting"])
        assert result["count"] == 1
        assert "Intermittent" in result["papers"][0]["title"]

    def test_keyword_filter_checks_abstract(self, paper_dicts):
        result = filter_papers(paper_dicts, keywords=["insulin"])
        # Only sample_paper has "insulin" in abstract
        assert result["count"] == 1

    def test_keyword_filter_no_match(self, paper_dicts):
        result = filter_papers(paper_dicts, keywords=["zzznomatch999"])
        assert result["count"] == 0

    def test_open_access_filter(self, paper_dicts):
        result = filter_papers(paper_dicts, open_access_only=True)
        assert all(p["is_open_access"] for p in result["papers"])

    def test_combined_filters(self, paper_dicts):
        result = filter_papers(paper_dicts, min_year=2020, open_access_only=True)
        # Only sample_paper (2024, open access)
        assert result["count"] == 1
        assert result["papers"][0]["year"] == 2024

    def test_original_count_preserved(self, paper_dicts):
        result = filter_papers(paper_dicts, min_citations=999)
        assert result["original_count"] == len(paper_dicts)
        assert result["count"] == 0


# ── rank_papers ───────────────────────────────────────────────────────────

class TestRankPapers:
    def test_empty_input(self):
        result = rank_papers([])
        assert result["papers"] == []
        assert result["count"] == 0

    def test_rank_by_citations_descending(self, paper_dicts):
        result = rank_papers(paper_dicts, sort_by="citations")
        counts = [p["citation_count"] for p in result["papers"]]
        assert counts == sorted(counts, reverse=True)

    def test_rank_by_citations_ascending(self, paper_dicts):
        result = rank_papers(paper_dicts, sort_by="citations", ascending=True)
        counts = [p["citation_count"] for p in result["papers"]]
        assert counts == sorted(counts)

    def test_rank_by_year_descending(self, paper_dicts):
        result = rank_papers(paper_dicts, sort_by="year")
        years = [p["year"] or 0 for p in result["papers"]]
        assert years == sorted(years, reverse=True)

    def test_rank_by_title(self, paper_dicts):
        # Default is descending (ascending=False), so titles should be Z→A
        result = rank_papers(paper_dicts, sort_by="title")
        titles = [p["title"].lower() for p in result["papers"]]
        assert titles == sorted(titles, reverse=True)

    def test_rank_by_title_ascending(self, paper_dicts):
        result = rank_papers(paper_dicts, sort_by="title", ascending=True)
        titles = [p["title"].lower() for p in result["papers"]]
        assert titles == sorted(titles)

    def test_unknown_sort_key_falls_back_to_citations(self, paper_dicts):
        result = rank_papers(paper_dicts, sort_by="bogus_key")
        counts = [p["citation_count"] for p in result["papers"]]
        assert counts == sorted(counts, reverse=True)

    def test_top_n_limits_results(self, paper_dicts):
        result = rank_papers(paper_dicts, top_n=2)
        assert result["count"] == 2
        assert len(result["papers"]) == 2

    def test_top_n_larger_than_list(self, paper_dicts):
        result = rank_papers(paper_dicts, top_n=100)
        assert result["count"] == len(paper_dicts)

    def test_sorted_by_field_in_response(self, paper_dicts):
        result = rank_papers(paper_dicts, sort_by="year")
        assert result["sorted_by"] == "year"


# ── extract_abstracts ─────────────────────────────────────────────────────

class TestExtractAbstracts:
    def test_empty_input(self):
        result = extract_abstracts([])
        assert result["digests"] == []
        assert result["total_papers"] == 0

    def test_papers_with_abstracts(self, paper_dicts):
        # sample_paper and the 2022 paper both have abstracts
        result = extract_abstracts(paper_dicts)
        assert result["with_abstract"] >= 2

    def test_paper_without_abstract_flagged(self, paper_dicts):
        # minimal paper (year=2018) has abstract=None
        result = extract_abstracts(paper_dicts)
        assert result["without_text"] >= 1
        no_abstract_digests = [d for d in result["digests"] if d["text_source"] == "none"]
        assert len(no_abstract_digests) >= 1
        assert "[No abstract available" in no_abstract_digests[0]["text"]

    def test_digest_includes_paper_id_and_title(self, paper_dicts):
        result = extract_abstracts(paper_dicts)
        for digest in result["digests"]:
            assert "paper_id" in digest
            assert "title" in digest
            assert "text" in digest

    def test_metadata_included_by_default(self, paper_dicts):
        result = extract_abstracts(paper_dicts)
        first = result["digests"][0]
        assert "year" in first
        assert "citation_count" in first
        assert "venue" in first

    def test_metadata_excluded(self, paper_dicts):
        result = extract_abstracts(paper_dicts, include_metadata=False)
        first = result["digests"][0]
        assert "year" not in first
        assert "citation_count" not in first

    def test_tldr_used_when_no_abstract(self):
        from research_agent.models.paper import Paper, Author
        p = Paper(
            paper_id="x",
            title="TLDR Paper",
            abstract=None,
            tldr="Short summary of the paper.",
        )
        result = extract_abstracts([p.model_dump()])
        assert result["with_tldr_only"] == 1
        assert result["digests"][0]["text_source"] == "tldr"
        assert result["digests"][0]["text"] == "Short summary of the paper."

    def test_total_papers_count(self, paper_dicts):
        result = extract_abstracts(paper_dicts)
        assert result["total_papers"] == len(paper_dicts)
