"""Optional critic agent for quality assurance and fact-checking."""

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.schemas import AgentName, AgentResult
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.services.llm_client import LLMClient


class CriticAgent(BaseAgent):
    """Fact-checking and quality-review agent.

    Validates that the final answer:
    - Cites sources properly
    - Doesn't contradict known facts
    - Meets quality thresholds
    """

    name = "critic"

    SYSTEM_PROMPT = """You are a research critic agent. Your job is to review research outputs
and provide quality feedback. Focus on:
1. Citation coverage - are sources properly cited?
2. Factual consistency - does the answer match the sources?
3. Completeness - are key points covered?
4. Hallucination detection - any unsupported claims?

Provide constructive feedback but do not rewrite the content."""

    def run(self, state: ResearchState) -> ResearchState:
        """Validate final answer and append findings to research_notes."""
        # If no final answer yet, skip
        if not state.final_answer:
            state.errors.append("critic: no final answer to review")
            return state

        # If no sources to validate against, skip
        if not state.sources:
            state.errors.append("critic: no sources to validate")
            return state

        llm = LLMClient()

        # Build source context
        source_context = "\n".join(
            f"- [{s.title}]({s.url}): {s.snippet}"
            for s in state.sources[:10]  # Limit to first 10 sources
        )

        user_prompt = f"""Review this research answer for quality:

Answer:
{state.final_answer}

Sources:
{source_context}

Provide feedback on:
1. Citation coverage (are sources properly cited?)
2. Factual consistency (does answer match sources?)
3. Completeness (are key points covered?)
4. Any hallucinations or unsupported claims?

Respond with a brief critique (3-5 sentences)."""

        response = llm.complete(
            system_prompt=self.SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        # Append critique to research_notes
        critique_header = "\n\n---\n## Critic Review\n"
        existing_notes = state.research_notes or ""
        state.research_notes = existing_notes + critique_header + response.content

        # Record agent result
        state.agent_results.append(
            AgentResult(
                agent=AgentName.CRITIC,
                content=response.content,
                metadata={
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "estimated_cost_usd": response.cost_usd,
                },
            )
        )

        return state
