"""Researcher agent - collects sources and creates research notes."""

import logging

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.schemas import AgentName, AgentResult, SourceDocument
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.search_client import SearchClient

logger = logging.getLogger(__name__)


class ResearcherAgent(BaseAgent):
    """Collects sources and creates concise research notes."""

    name = "researcher"

    def run(self, state: ResearchState) -> ResearchState:
        """Populate `state.sources` and `state.research_notes`."""
        try:
            search_client = SearchClient()
            max_sources = state.request.max_sources
            query = state.request.query

            logger.info("Researcher: searching for '%s' (max %d sources)", query, max_sources)

            # Search for relevant sources
            sources = search_client.search(query=query, max_results=max_sources)

            if not sources:
                state.errors.append("Researcher: search returned no results")
                logger.warning("Researcher: no sources found for query '%s'", query)
                return state

            # Update state with sources
            state.sources = sources

            # Generate research notes from sources
            research_notes = self._generate_research_notes(query, sources)
            state.research_notes = research_notes

            # Record agent result
            state.agent_results.append(
                AgentResult(
                    agent=AgentName.RESEARCHER,
                    content=research_notes,
                    metadata={"source_count": len(sources)},
                )
            )

            logger.info(
                "Researcher: found %d sources, notes length=%d",
                len(sources),
                len(research_notes),
            )
            return state

        except Exception:  # noqa: BLE001
            logger.exception("Researcher failed")
            # Re-raise so workflow can handle the error
            raise

    def _generate_research_notes(self, query: str, sources: list[SourceDocument]) -> str:
        """Generate research notes from sources."""
        # Build context from sources
        context_parts = []
        for i, source in enumerate(sources, 1):
            context_parts.append(f"[Source {i}] {source.title}\n{source.snippet}")

        context = "\n\n".join(context_parts)

        notes = f"""Research Query: {query}

Sources Found:
{context}

---
Research Notes:
Based on the sources above, the following key information relates to the query:
"""
        return notes
