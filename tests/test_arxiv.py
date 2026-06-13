"""Tests for search_arxiv — ArXiv search tool (mocked)."""

from unittest.mock import MagicMock, patch
import pytest

from research_agent.tools.arxiv_search import search_arxiv, _to_paper
from research_agent.models.paper import Author, Paper


def _make_arxiv_result(
    short_id: str = "2401.00001v1",
    title: str = "Test Paper",
    authors: list[str] | None = None,
    summary: str = "An abstract.",
    year: int = 2024,
    entry_id: str = "http://arxiv.org/abs/2401.00001v1",
    categories: list[str] | None = None,
) -> MagicMock:
    """Build a minimal arxiv.Result mock."""
    result = MagicMock()
    result.get_short_id.return_value = short_id
    result.title = title
    # Must assign .name AFTER construction — MagicMock(name=...) sets the
    # mock's own internal name, not the attribute `a.name`.
    mock_authors = []
    for author_name in (authors or ["Alice Author"]):
        a = MagicMock()
        a.name = author_name
        mock_authors.append(a)
    result.authors = mock_authors
    result.summary = summary
    result.published = MagicMock()
    result.published.year = year
    result.entry_id = entry_id
    result.categories = categories or ["cs.LG"]
    return result


class TestTopaper:
    def test_converts_basic_fields(self):
        mock_result = _make_arxiv_result(
            short_id="2401.00001v1",
            title="Deep Learning",
            authors=["Jane Doe"],
            summary="A paper about deep learning.\nLine two.",
            year=2023,
        )
        paper = _to_paper(mock_result)
        assert paper.paper_id == "2401.00001v1"
        assert paper.title == "Deep Learning"
        assert paper.year == 2023
        assert paper.is_open_access is True
        assert paper.venue == "arxiv"
        assert "\n" not in paper.abstract  # newlines replaced

    def test_author_names_mapped(self):
        mock_result = _make_arxiv_result(authors=["Alice", "Bob"])
        paper = _to_paper(mock_result)
        assert len(paper.authors) == 2
        assert paper.authors[0].name == "Alice"
        assert paper.authors[1].name == "Bob"

    def test_categories_become_fields_of_study(self):
        mock_result = _make_arxiv_result(categories=["cs.LG", "stat.ML"])
        paper = _to_paper(mock_result)
        assert "cs.LG" in paper.fields_of_study
        assert "stat.ML" in paper.fields_of_study


class TestSearchArxiv:
    def _make_client(self, results: list) -> MagicMock:
        client = MagicMock()
        client.results.return_value = iter(results)
        return client

    @patch("research_agent.tools.arxiv_search.arxiv.Client")
    @patch("research_agent.tools.arxiv_search.arxiv.Search")
    def test_returns_correct_structure(self, mock_search, mock_client_cls):
        mock_result = _make_arxiv_result()
        mock_client_cls.return_value = self._make_client([mock_result])

        result = search_arxiv("neural networks", max_results=5)

        assert "papers" in result
        assert "query" in result
        assert "total_results" in result
        assert result["source"] == "arxiv"
        assert result["query"] == "neural networks"
        assert len(result["papers"]) == 1

    @patch("research_agent.tools.arxiv_search.arxiv.Client")
    @patch("research_agent.tools.arxiv_search.arxiv.Search")
    def test_max_results_capped_at_30(self, mock_search, mock_client_cls):
        mock_client_cls.return_value = self._make_client([])
        search_arxiv("test", max_results=999)
        # Verify Search was called with max_results <= 30
        call_kwargs = mock_search.call_args
        assert call_kwargs.kwargs["max_results"] <= 30

    @patch("research_agent.tools.arxiv_search.arxiv.Client")
    @patch("research_agent.tools.arxiv_search.arxiv.Search")
    def test_empty_results(self, mock_search, mock_client_cls):
        mock_client_cls.return_value = self._make_client([])
        result = search_arxiv("obscure query xyz123")
        assert result["papers"] == []
        assert result["total_results"] == 0

    @patch("research_agent.tools.arxiv_search.arxiv.Client")
    @patch("research_agent.tools.arxiv_search.arxiv.Search")
    def test_exception_returns_error_dict(self, mock_search, mock_client_cls):
        mock_client_cls.side_effect = RuntimeError("connection refused")
        result = search_arxiv("test")
        assert result["papers"] == []
        assert "error" in result
        assert "connection refused" in result["error"]

    @patch("research_agent.tools.arxiv_search.arxiv.Client")
    @patch("research_agent.tools.arxiv_search.arxiv.Search")
    def test_multiple_results_all_returned(self, mock_search, mock_client_cls):
        mock_results = [_make_arxiv_result(short_id=f"24{i:02d}.00001") for i in range(5)]
        mock_client_cls.return_value = self._make_client(mock_results)
        result = search_arxiv("test", max_results=10)
        assert len(result["papers"]) == 5
