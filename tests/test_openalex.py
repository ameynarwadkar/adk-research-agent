"""Tests for search_openalex — OpenAlex search tool (mocked)."""

from unittest.mock import MagicMock, patch
import pytest

from research_agent.tools.openalex_search import search_openalex, _reconstruct_abstract


# ── _reconstruct_abstract ────────────────────────────────────────────────

class TestReconstructAbstract:
    def test_none_returns_none(self):
        assert _reconstruct_abstract(None) is None

    def test_empty_dict_returns_none(self):
        assert _reconstruct_abstract({}) is None

    def test_basic_reconstruction(self):
        # "Hello world" → {"Hello": [0], "world": [1]}
        inverted = {"Hello": [0], "world": [1]}
        assert _reconstruct_abstract(inverted) == "Hello world"

    def test_out_of_order_positions(self):
        inverted = {"world": [1], "Hello": [0]}
        assert _reconstruct_abstract(inverted) == "Hello world"

    def test_multiple_positions_for_word(self):
        # "the cat and the dog"
        inverted = {"the": [0, 3], "cat": [1], "and": [2], "dog": [4]}
        result = _reconstruct_abstract(inverted)
        assert result == "the cat and the dog"

    def test_single_word(self):
        assert _reconstruct_abstract({"science": [0]}) == "science"


# ── search_openalex ──────────────────────────────────────────────────────

_MOCK_OPENALEX_RESPONSE = {
    "meta": {"count": 1},
    "results": [
        {
            "id": "https://openalex.org/W1234567",
            "doi": "https://doi.org/10.1000/test",
            "title": "Fasting and Metabolic Health",
            "authorships": [
                {"author": {"display_name": "Jane Smith"}},
                {"author": {"display_name": "Bob Jones"}},
            ],
            "publication_year": 2023,
            "cited_by_count": 55,
            "primary_location": {
                "source": {"display_name": "Journal of Nutrition"}
            },
            "open_access": {"is_oa": True},
            "abstract_inverted_index": {"Fasting": [0], "helps": [1], "metabolism": [2]},
            "concepts": [
                {"display_name": "Medicine", "score": 0.9},
                {"display_name": "Nutrition", "score": 0.7},
            ],
            "best_oa_url": "https://example.com/paper.pdf",
        }
    ],
}


class TestSearchOpenalex:
    def _mock_response(self, data: dict) -> MagicMock:
        resp = MagicMock()
        resp.json.return_value = data
        resp.raise_for_status = MagicMock()
        resp.status_code = 200
        return resp

    @patch("research_agent.tools.openalex_search.httpx.Client")
    def test_returns_correct_structure(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = self._mock_response(_MOCK_OPENALEX_RESPONSE)
        mock_client_cls.return_value = mock_client

        result = search_openalex("intermittent fasting")

        assert result["source"] == "openalex"
        assert result["query"] == "intermittent fasting"
        assert "papers" in result
        assert "total_results" in result

    @patch("research_agent.tools.openalex_search.httpx.Client")
    def test_paper_fields_mapped_correctly(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = self._mock_response(_MOCK_OPENALEX_RESPONSE)
        mock_client_cls.return_value = mock_client

        result = search_openalex("fasting")
        paper = result["papers"][0]

        assert paper["paper_id"] == "W1234567"
        assert paper["title"] == "Fasting and Metabolic Health"
        assert paper["year"] == 2023
        assert paper["citation_count"] == 55
        assert paper["venue"] == "Journal of Nutrition"
        assert paper["is_open_access"] is True
        assert len(paper["authors"]) == 2
        assert paper["abstract"] == "Fasting helps metabolism"

    @patch("research_agent.tools.openalex_search.httpx.Client")
    def test_max_results_capped_at_50(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = self._mock_response({"meta": {"count": 0}, "results": []})
        mock_client_cls.return_value = mock_client

        search_openalex("test", max_results=9999)
        call_kwargs = mock_client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs.args[1] if len(call_kwargs.args) > 1 else {}
        assert params.get("per-page", 0) <= 50

    @patch("research_agent.tools.openalex_search.httpx.Client")
    def test_http_error_returns_error_dict(self, mock_client_cls):
        import httpx
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.HTTPError("timeout")
        mock_client_cls.return_value = mock_client

        result = search_openalex("test")
        assert result["papers"] == []
        assert "error" in result

    @patch("research_agent.tools.openalex_search.httpx.Client")
    def test_empty_results(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = self._mock_response({"meta": {"count": 0}, "results": []})
        mock_client_cls.return_value = mock_client

        result = search_openalex("xyzabcnothing")
        assert result["papers"] == []
        assert result["total_results"] == 0
