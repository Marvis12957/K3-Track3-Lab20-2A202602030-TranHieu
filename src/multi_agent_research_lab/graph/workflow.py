"""LangGraph workflow for multi-agent research system."""

from __future__ import annotations

import logging
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from multi_agent_research_lab.agents.analyst import AnalystAgent
from multi_agent_research_lab.agents.researcher import ResearcherAgent
from multi_agent_research_lab.agents.supervisor import SupervisorAgent
from multi_agent_research_lab.agents.writer import WriterAgent
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.observability.tracing import trace_span

logger = logging.getLogger(__name__)


def _update_state(current: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Merge updates into current state, preserving list fields."""
    merged = current.copy()
    for key, value in updates.items():
        if key in merged and isinstance(merged[key], list) and isinstance(value, list):
            # Preserve existing list items by tracking seen content
            existing_content = {str(item) for item in merged[key]}
            for item in value:
                item_key = str(item)
                if item_key not in existing_content:
                    merged[key].append(item)
                    existing_content.add(item_key)
        else:
            merged[key] = value
    return merged


def _supervisor_node(state: ResearchState) -> dict[str, Any]:
    """Supervisor node - decides next route."""
    with trace_span("agent.supervisor", {"iteration": state.iteration}) as span:
        agent = SupervisorAgent()
        result = agent.run(state)
        span["route"] = result.route_history[-1] if result.route_history else "unknown"
        span["status"] = "success"
        # Record trace event
        result.add_trace_event(
            "agent.supervisor",
            {
                "iteration": state.iteration,
                "duration_seconds": span["duration_seconds"],
                "status": "success",
                "route": span["route"],
            },
        )
        # Return full state to preserve lists
        return result.model_dump()


def _researcher_node(state: ResearchState) -> dict[str, Any]:
    """Researcher node - collects sources and notes."""
    with trace_span("agent.researcher", {"iteration": state.iteration}) as span:
        try:
            agent = ResearcherAgent()
            result = agent.run(state)
            span["status"] = "success"
            span["num_sources"] = len(result.sources)
            # Record trace event
            result.add_trace_event(
                "agent.researcher",
                {
                    "iteration": state.iteration,
                    "duration_seconds": span["duration_seconds"],
                    "status": "success",
                    "num_sources": len(result.sources),
                },
            )
            # Return full state on success
            return result.model_dump()
        except Exception as exc:  # noqa: BLE001
            span["status"] = "error"
            span["error"] = str(exc)
            logger.exception("Researcher failed")
            # Record trace event for error
            state.add_trace_event(
                "agent.researcher",
                {
                    "iteration": state.iteration,
                    "duration_seconds": span["duration_seconds"],
                    "status": "error",
                    "error": str(exc),
                },
            )
            # Only return errors, not full state, to preserve previous agent_results
            return {"errors": [f"researcher: {exc}"]}


def _analyst_node(state: ResearchState) -> dict[str, Any]:
    """Analyst node - creates analysis notes."""
    with trace_span("agent.analyst", {"iteration": state.iteration}) as span:
        try:
            agent = AnalystAgent()
            result = agent.run(state)
            span["status"] = "success"
            # Record trace event
            result.add_trace_event(
                "agent.analyst",
                {
                    "iteration": state.iteration,
                    "duration_seconds": span["duration_seconds"],
                    "status": "success",
                    "has_analysis": result.analysis_notes is not None,
                },
            )
            # Return full state on success
            return result.model_dump()
        except Exception as exc:  # noqa: BLE001
            span["status"] = "error"
            span["error"] = str(exc)
            logger.exception("Analyst failed")
            # Record trace event for error
            state.add_trace_event(
                "agent.analyst",
                {
                    "iteration": state.iteration,
                    "duration_seconds": span["duration_seconds"],
                    "status": "error",
                    "error": str(exc),
                },
            )
            # Only return errors, not full state, to preserve previous agent_results
            return {"errors": [f"analyst: {exc}"]}


def _writer_node(state: ResearchState) -> dict[str, Any]:
    """Writer node - produces final answer."""
    with trace_span("agent.writer", {"iteration": state.iteration}) as span:
        try:
            agent = WriterAgent()
            result = agent.run(state)
            span["status"] = "success"
            # Record trace event
            result.add_trace_event(
                "agent.writer",
                {
                    "iteration": state.iteration,
                    "duration_seconds": span["duration_seconds"],
                    "status": "success",
                    "has_answer": result.final_answer is not None,
                },
            )
            # Return full state on success
            return result.model_dump()
        except Exception as exc:  # noqa: BLE001
            span["status"] = "error"
            span["error"] = str(exc)
            logger.exception("Writer failed")
            # Record trace event for error
            state.add_trace_event(
                "agent.writer",
                {
                    "iteration": state.iteration,
                    "duration_seconds": span["duration_seconds"],
                    "status": "error",
                    "error": str(exc),
                },
            )
            # Only return errors, not full state, to preserve previous agent_results
            return {"errors": [f"writer: {exc}"]}


def _route(state: ResearchState) -> Literal["researcher", "analyst", "writer", "done"]:
    """Route based on last entry in route_history.

    Returns the last route decision from Supervisor.
    """
    if not state.route_history:
        return "done"
    # Cast is safe because Supervisor only sets valid routes
    return state.route_history[-1]  # type: ignore[return-value]


class MultiAgentWorkflow:
    """Builds and runs the multi-agent graph.

    Keep orchestration here; keep agent internals in `agents/`.
    """

    def __init__(self) -> None:
        self._graph: Any = self.build()

    def build(self) -> Any:
        """Create a LangGraph StateGraph."""
        workflow = StateGraph(ResearchState)

        # Add nodes
        workflow.add_node("supervisor", _supervisor_node)
        workflow.add_node("researcher", _researcher_node)
        workflow.add_node("analyst", _analyst_node)
        workflow.add_node("writer", _writer_node)

        # Set entry point
        workflow.set_entry_point("supervisor")

        # Add edges from supervisor based on routing decision
        workflow.add_conditional_edges(
            "supervisor",
            _route,
            {
                "researcher": "researcher",
                "analyst": "analyst",
                "writer": "writer",
                "done": END,
            },
        )

        # After each worker, return to supervisor for next decision
        workflow.add_edge("researcher", "supervisor")
        workflow.add_edge("analyst", "supervisor")
        workflow.add_edge("writer", "supervisor")

        return workflow.compile()

    def run(self, state: ResearchState) -> ResearchState:
        """Execute the graph and return final state."""
        logger.info("Starting multi-agent workflow")
        result_dict = self._graph.invoke(state)
        # Convert dict back to ResearchState
        result = ResearchState.model_validate(result_dict)
        logger.info(
            "Workflow complete: iterations=%d, route_history=%s",
            result.iteration,
            result.route_history,
        )
        return result
