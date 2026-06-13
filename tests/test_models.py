"""Tests for research_agent.models — Paper, Author, PaperCollection."""

import pytest

from research_agent.models.paper import Author, Paper, PaperCollection


# ── Author ────────────────────────────────────────────────────────────────

class TestAuthor:
    def test_str_returns_name(self):
        author = Author(name="Jane Smith")
        assert str(author) == "Jane Smith"

    def test_author_id_optional(self):
        author = Author(name="Jane Smith")
        assert author.author_id is None

    def test_author_id_set(self):
        author = Author(name="Jane Smith", author_id="orcid:0000-0001")
        assert author.author_id == "orcid:0000-0001"


# ── Paper.authors_str ─────────────────────────────────────────────────────

class TestPaperAuthorsStr:
    def test_no_authors(self, minimal_paper):
        assert minimal_paper.authors_str == "Unknown"

    def test_one_author(self):
        p = Paper(paper_id="x", title="T", authors=[Author(name="Alice")])
        assert p.authors_str == "Alice"

    def test_two_authors(self):
        p = Paper(
            paper_id="x",
            title="T",
            authors=[Author(name="Alice"), Author(name="Bob")],
        )
        assert p.authors_str == "Alice and Bob"

    def test_three_or_more_authors(self, sample_paper):
        # sample_paper has [Alice Brown, Bob Chen, Carol Davis]
        p = sample_paper.authors_str
        assert "Alice Brown" in p
        assert "Bob Chen" in p
        assert "Carol Davis" in p
        assert p.endswith(", and Carol Davis")


# ── Paper.citation_str ────────────────────────────────────────────────────

class TestPaperCitationStr:
    def test_no_authors_unknown(self, minimal_paper):
        assert "Unknown" in minimal_paper.citation_str

    def test_no_year_nd(self, minimal_paper):
        assert "n.d." in minimal_paper.citation_str

    def test_single_author_no_et_al(self):
        p = Paper(
            paper_id="x",
            title="T",
            authors=[Author(name="John Smith")],
            year=2023,
        )
        assert p.citation_str == "Smith (2023)"
        assert "et al" not in p.citation_str

    def test_three_authors_et_al(self, sample_paper):
        # Alice Brown, Bob Chen, Carol Davis → "Brown et al. (2024)"
        assert sample_paper.citation_str == "Brown et al. (2024)"

    def test_str_combines_citation_and_title(self, sample_paper):
        s = str(sample_paper)
        assert "Brown et al." in s
        assert sample_paper.title in s


# ── Paper field defaults ──────────────────────────────────────────────────

class TestPaperDefaults:
    def test_defaults(self, minimal_paper):
        assert minimal_paper.authors == []
        assert minimal_paper.abstract is None
        assert minimal_paper.year is None
        assert minimal_paper.citation_count == 0
        assert minimal_paper.is_open_access is False
        assert minimal_paper.fields_of_study == []
        assert minimal_paper.tldr is None
        assert minimal_paper.venue is None

    def test_model_dump_round_trip(self, sample_paper):
        dumped = sample_paper.model_dump()
        restored = Paper.model_validate(dumped)
        assert restored.paper_id == sample_paper.paper_id
        assert restored.title == sample_paper.title
        assert len(restored.authors) == len(sample_paper.authors)
        assert restored.citation_count == sample_paper.citation_count


# ── PaperCollection ───────────────────────────────────────────────────────

class TestPaperCollection:
    def test_count_property(self, paper_list):
        col = PaperCollection(
            papers=paper_list,
            query="test query",
        )
        assert col.count == len(paper_list)

    def test_empty_collection(self):
        col = PaperCollection(papers=[], query="nothing")
        assert col.count == 0
        assert col.total_results == 0
        assert col.filters_applied == []
