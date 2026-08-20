"""Unit tests for SupervisorAgent routing logic."""

from multi_agent_research_lab.agents.supervisor import SupervisorAgent
from multi_agent_research_lab.core.schemas import ResearchQuery, SourceDocument
from multi_agent_research_lab.core.state import ResearchState


def _create_state(
    query: str = "Test query",
    sources: list[SourceDocument] | None = None,
    research_notes: str | None = None,
    analysis_notes: str | None = None,
    final_answer: str | None = None,
    iteration: int = 0,
) -> ResearchState:
    """Helper to create test state."""
    return ResearchState(
        request=ResearchQuery(query=query),
        iteration=iteration,
        sources=sources or [],
        research_notes=research_notes,
        analysis_notes=analysis_notes,
        final_answer=final_answer,
    )


def test_supervisor_no_sources_routes_to_researcher() -> None:
    """Case 1: No sources -> researcher"""
    state = _create_state()
    result = SupervisorAgent().run(state)
    assert result.route_history[-1] == "researcher"
    assert result.iteration == 1


def test_supervisor_has_sources_no_analysis_routes_to_analyst() -> None:
    """Case 2: Has sources, no analysis -> analyst"""
    sources = [SourceDocument(title="Test", snippet="Test snippet")]
    state = _create_state(sources=sources, research_notes="Some notes")
    result = SupervisorAgent().run(state)
    assert result.route_history[-1] == "analyst"
    assert result.iteration == 1


def test_supervisor_has_research_no_answer_routes_to_writer() -> None:
    """Case 3: Has research + analysis, no final answer -> writer"""
    state = _create_state(
        sources=[SourceDocument(title="Test", snippet="Test")],
        research_notes="Research notes",
        analysis_notes="Analysis notes",
    )
    result = SupervisorAgent().run(state)
    assert result.route_history[-1] == "writer"
    assert result.iteration == 1


def test_supervisor_has_final_answer_routes_to_done() -> None:
    """Case 4: Has final answer -> done (no iteration increment)"""
    state = _create_state(
        sources=[SourceDocument(title="Test", snippet="Test")],
        research_notes="Research notes",
        analysis_notes="Analysis notes",
        final_answer="Final answer here",
    )
    result = SupervisorAgent().run(state)
    assert result.route_history[-1] == "done"
    # "done" routes do not increment iteration
    assert result.iteration == 0


def test_supervisor_max_iterations_routes_to_done() -> None:
    """Case 5: Iteration >= max_iterations -> done (no iteration increment)"""
    state = _create_state(iteration=6)  # max_iterations default is 6
    result = SupervisorAgent().run(state)
    assert result.route_history[-1] == "done"
    # "done" routes do not increment iteration
    assert result.iteration == 6


def test_supervisor_records_route_history() -> None:
    """Verify route_history is properly recorded."""
    state = _create_state()
    result = SupervisorAgent().run(state)

    assert len(result.route_history) == 1
    assert "researcher" in result.route_history


def test_supervisor_increments_iteration() -> None:
    """Verify iteration is incremented on each run."""
    state = _create_state(iteration=2)
    result = SupervisorAgent().run(state)

    assert result.iteration == 3
