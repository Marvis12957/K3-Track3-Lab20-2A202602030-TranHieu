"""Search client for ResearcherAgent.

Supports Tavily API with mock fallback for development/testing.
"""

import logging

from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.schemas import SourceDocument

logger = logging.getLogger(__name__)


class SearchClient:
    """Search client using Tavily API with mock fallback."""

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.tavily_api_key

    def search(self, query: str, max_results: int = 5) -> list[SourceDocument]:
        """Search for documents relevant to a query.

        Uses Tavily API if available, otherwise returns mock results for development.
        """
        if not self._api_key:
            logger.warning("Tavily API key not configured, using mock search")
            return self._mock_search(query, max_results)

        try:
            return self._tavily_search(query, max_results)
        except Exception as exc:  # noqa: BLE001
            logger.error("Search failed: %s", exc)
            return self._mock_search(query, max_results)

    def _tavily_search(self, query: str, max_results: int) -> list[SourceDocument]:
        """Search using Tavily API."""
        import httpx

        url = "https://api.tavily.com/search"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        payload = {"query": query, "max_results": max_results, "include_answer": True}

        with httpx.Client(timeout=30) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        results = data.get("results", [])
        sources = []
        for item in results[:max_results]:
            sources.append(
                SourceDocument(
                    title=item.get("title", "Untitled"),
                    url=item.get("url"),
                    snippet=item.get("content", "")[:500],
                    metadata={"score": item.get("score", 0)},
                )
            )
        return sources

    def _mock_search(self, query: str, max_results: int) -> list[SourceDocument]:
        """Mock search results for development/testing.

        Returns simulated sources based on the query.
        """
        logger.info("Using mock search for query: %s", query)

        # Generate mock sources based on query keywords
        mock_sources = [
            SourceDocument(
                title=f"Understanding {query[:50]} - Overview",
                url="https://example.com/overview",
                snippet=f"This article provides an overview of {query}. "
                f"It covers the fundamental concepts and applications.",
                metadata={"source": "mock", "type": "article"},
            ),
            SourceDocument(
                title=f"Research on {query[:50]} - Technical Deep Dive",
                url="https://example.com/technical",
                snippet=f"Technical analysis of {query}. "
                f"Includes implementation details and best practices.",
                metadata={"source": "mock", "type": "technical"},
            ),
            SourceDocument(
                title=f"{query[:50]} - Recent Developments",
                url="https://example.com/recent",
                snippet=f"Latest news and developments around {query}. "
                f"Current trends and future directions.",
                metadata={"source": "mock", "type": "news"},
            ),
        ]

        return mock_sources[:max_results]
