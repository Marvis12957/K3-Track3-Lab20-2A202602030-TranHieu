"""Writer agent - synthesizes final answer from research and analysis."""

import logging

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class WriterAgent(BaseAgent):
    """Produces final answer from research and analysis notes."""

    name = "writer"

    SYSTEM_PROMPT = (
        "Expert technical writer synthesizing research into clear responses. "
        "Answer directly. Base on research. Include citations."
    )

    def run(self, state: ResearchState) -> ResearchState:
        """Populate `state.final_answer`."""
        try:
            # Check if we have what we need
            if not state.research_notes:
                state.errors.append("Writer: no research notes available")
                logger.warning("Writer: skipping - no research notes")
                return state

            logger.info(
                "Writer: synthesizing answer (research=%d, analysis=%s, sources=%d)",
                len(state.research_notes),
                "yes" if state.analysis_notes else "no",
                len(state.sources),
            )

            # Build context for synthesis
            context = self._build_context(state)

            # Use LLM to synthesize
            llm = LLMClient()
            user_prompt = self._build_synthesis_prompt(state.request.query, context)
            response = llm.complete(system_prompt=self.SYSTEM_PROMPT, user_prompt=user_prompt)

            # Update state
            state.final_answer = response.content

            # Record agent result
            state.agent_results.append(
                AgentResult(
                    agent=AgentName.WRITER,
                    content=response.content,
                    metadata={
                        "answer_length": len(response.content),
                        "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens,
                    },
                )
            )

            logger.info("Writer: synthesis complete, answer length=%d", len(response.content))
            return state

        except Exception:  # noqa: BLE001
            logger.exception("Writer failed")
            # Re-raise so workflow can handle the error
            raise

    def _build_context(self, state: ResearchState) -> str:
        """Build context from research and analysis."""
        parts = []

        # Add sources
        if state.sources:
            source_parts = ["## Sources\n"]
            for i, source in enumerate(state.sources, 1):
                source_parts.append(f"[{i}] {source.title}: {source.url or 'N/A'}")
            parts.append("\n".join(source_parts))

        # Add research notes
        if state.research_notes:
            parts.append(f"\n## Research Notes\n{state.research_notes}")

        # Add analysis notes
        if state.analysis_notes:
            parts.append(f"\n## Analysis\n{state.analysis_notes}")

        return "\n".join(parts)

    def _build_synthesis_prompt(self, query: str, context: str) -> str:
        """Build synthesis prompt for LLM."""
        return (
            f"Query: {query}\n\n{context}\n\n"
            "Based on the above research and analysis, provide a comprehensive response. "
            "Include relevant citations."
        )
