"""
Tavily web search tool wrapper.
Returns top-5 results with title, URL, and content snippet.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the web using Tavily and return formatted results.
    Returns a string summary suitable for inclusion in an LLM prompt.
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "Error: TAVILY_API_KEY is not set. Cannot perform web search."

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)

        response = client.search(
            query=query,
            max_results=max_results,
            search_depth="advanced",
            include_answer=True,
        )

        parts = []

        # Include Tavily's auto-generated answer if available
        if response.get("answer"):
            parts.append(f"Summary: {response['answer']}\n")

        # Include individual results
        for i, result in enumerate(response.get("results", []), 1):
            title = result.get("title", "No title")
            url = result.get("url", "")
            content = result.get("content", "")[:800]  # Truncate long snippets
            parts.append(f"[{i}] {title}\nURL: {url}\n{content}\n")

        return "\n".join(parts) if parts else "No results found."

    except Exception as e:
        logger.error(f"Web search failed for query '{query}': {e}")
        return f"Web search failed: {str(e)}"
