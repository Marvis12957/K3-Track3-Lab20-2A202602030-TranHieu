"""Supervisor / router agent with deterministic routing."""

import logging

from multi_agent_research_lab.agents.base import BaseAgent
from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.state import ResearchState

logger = logging.getLogger(__name__)


class SupervisorAgent(BaseAgent):
    """Decides which worker should run next and when to stop.

    Deterministic routing based on shared state - NO LLM call.
    """

    name = "supervisor"

    def run(self, state: ResearchState) -> ResearchState:
        """Inspect state and route to next agent or terminate.

        Routing logic:
        1. If max iterations reached -> done (no iteration increment)
        2. If no sources -> researcher
        3. If no analysis_notes -> analyst
        4. If no final_answer -> writer
        5. Otherwise -> done (no iteration increment)

        Records the routing decision in route_history.
        Only increments iteration for WORKER routes, not termination.
        """
        settings = get_settings()

        # Determine next route
        if state.iteration >= settings.max_iterations:
            route = "done"
            logger.info(
                "Supervisor: max iterations (%d) reached, terminating",
                settings.max_iterations,
            )
        elif not state.sources:
            route = "researcher"
            logger.info("Supervisor: no sources, routing to researcher")
        elif not state.analysis_notes:
            route = "analyst"
            logger.info("Supervisor: no analysis, routing to analyst")
        elif not state.final_answer:
            route = "writer"
            logger.info("Supervisor: no final answer, routing to writer")
        else:
            route = "done"
            logger.info("Supervisor: all tasks complete, terminating")

        # Record route decision
        # Only increment iteration for worker routes, not termination
        # This ensures: iteration <= max_iterations always
        state.route_history.append(route)
        if route != "done":
            state.iteration += 1

        return state
