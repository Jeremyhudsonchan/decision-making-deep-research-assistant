"""
Tests for the Tavily web search tool wrapper.
All tests mock TavilyClient to avoid real network calls.
"""

import pytest
from unittest.mock import MagicMock, patch


def _make_tavily_response(answer=None, results=None):
    """Build a minimal Tavily response dict."""
    return {
        "answer": answer,
        "results": results or [],
    }


class TestWebSearch:
    def test_returns_formatted_string_with_results(self, monkeypatch):
        from app.agent.tools.web_search import web_search

        fake_response = _make_tavily_response(
            results=[
                {
                    "title": "AI Overview",
                    "url": "https://example.com/ai",
                    "content": "Artificial intelligence is transforming industries.",
                }
            ]
        )

        with patch("tavily.TavilyClient") as MockClient:
            MockClient.return_value.search.return_value = fake_response
            result = web_search("What is AI?")

        assert "AI Overview" in result
        assert "https://example.com/ai" in result
        assert "Artificial intelligence" in result

    def test_includes_tavily_answer_at_top(self, monkeypatch):
        from app.agent.tools.web_search import web_search

        fake_response = _make_tavily_response(
            answer="AI stands for Artificial Intelligence.",
            results=[
                {"title": "T", "url": "https://example.com", "content": "body"}
            ],
        )

        with patch("tavily.TavilyClient") as MockClient:
            MockClient.return_value.search.return_value = fake_response
            result = web_search("What is AI?")

        assert "Summary: AI stands for Artificial Intelligence." in result

    def test_truncates_long_snippets(self, monkeypatch):
        from app.agent.tools.web_search import web_search

        long_content = "x" * 1200
        fake_response = _make_tavily_response(
            results=[{"title": "Long", "url": "https://x.com", "content": long_content}]
        )

        with patch("tavily.TavilyClient") as MockClient:
            MockClient.return_value.search.return_value = fake_response
            result = web_search("query")

        # The tool truncates content to 800 chars
        assert "x" * 801 not in result
        assert "x" * 800 in result

    def test_missing_api_key_returns_error_string(self, monkeypatch):
        from app.agent.tools.web_search import web_search

        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        result = web_search("test")

        assert "Error" in result
        assert "TAVILY_API_KEY" in result

    def test_api_failure_returns_error_string(self):
        from app.agent.tools.web_search import web_search

        with patch("tavily.TavilyClient") as MockClient:
            MockClient.return_value.search.side_effect = RuntimeError(
                "Connection refused"
            )
            result = web_search("query")

        assert "Web search failed" in result
        assert "Connection refused" in result

    def test_no_results_returns_no_results_string(self):
        from app.agent.tools.web_search import web_search

        with patch("tavily.TavilyClient") as MockClient:
            MockClient.return_value.search.return_value = _make_tavily_response()
            result = web_search("obscure query")

        assert result == "No results found."
