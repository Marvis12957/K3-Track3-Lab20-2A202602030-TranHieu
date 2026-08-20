"""Analyst agent - extracts claims and analyzes evidence."""

import logging

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class AnalystAgent(BaseAgent):
    """Turns research notes into structured insights."""

    name = "analyst"

    SYSTEM_PROMPT = (
        "Expert research analyst. Analyze notes and sources: extract claims, compare evidence, "
        "identify weak/conflicting evidence, distinguish inference from fact. No hallucination."
    )

    def run(self, state: ResearchState) -> ResearchState:
        """Populate `state.analysis_notes`."""
        try:
            # Check if we have research notes to analyze
            if not state.research_notes:
                state.errors.append("Analyst: no research notes available")
                logger.warning("Analyst: skipping - no research notes")
                return state

            if not state.sources:
                state.errors.append("Analyst: no sources available")
                logger.warning("Analyst: skipping - no sources")
                return state

            logger.info(
                "Analyst: analyzing %d sources, notes length=%d",
                len(state.sources),
                len(state.research_notes),
            )

            # Build source context for analysis
            source_context = self._build_source_context(state)

            # Use LLM to analyze
            llm = LLMClient()
            user_prompt = self._build_analysis_prompt(state.research_notes, source_context)
            response = llm.complete(system_prompt=self.SYSTEM_PROMPT, user_prompt=user_prompt)

            # Update state
            state.analysis_notes = response.content

            # Record agent result
            state.agent_results.append(
                AgentResult(
                    agent=AgentName.ANALYST,
                    content=response.content,
                    metadata={
                        "input_source_count": len(state.sources),
                        "analysis_length": len(response.content),
                        "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens,
                    },
                )
            )

            logger.info("Analyst: analysis complete, length=%d", len(response.content))
            return state

        except Exception:  # noqa: BLE001
            logger.exception("Analyst failed")
            # Re-raise so workflow can handle the error
            raise

    def _build_source_context(self, state: ResearchState) -> str:
        """Build source context for analysis."""
        context_parts = []
        for i, source in enumerate(state.sources, 1):
            context_parts.append(f"[Source {i}] {source.title}\n{source.snippet}")
        return "\n\n".join(context_parts)

    def _build_analysis_prompt(self, research_notes: str, source_context: str) -> str:
        """Build analysis prompt for LLM."""
        return (
            f"Research Notes:\n{research_notes}\n\nSources:\n{source_context}\n\n"
            "Analyze the above notes and sources. Provide: key claims, evidence comparison, "
            "weak/uncertain evidence (flagged), conflicts, and gaps. Use clear sections."
        )
