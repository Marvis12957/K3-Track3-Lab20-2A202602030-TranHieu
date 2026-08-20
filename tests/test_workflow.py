"""Unit tests for MultiAgentWorkflow."""

from unittest.mock import MagicMock, patch

from multi_agent_research_lab.core.schemas import AgentName, ResearchQuery, SourceDocument
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.graph.workflow import MultiAgentWorkflow


def test_workflow_builds_successfully() -> None:
    """Verify workflow can be built without errors."""
    workflow = MultiAgentWorkflow()
    assert workflow._graph is not None


def test_workflow_terminates_on_max_iterations() -> None:
    """Verify workflow terminates when max iterations reached."""
    state = ResearchState(request=ResearchQuery(query="Test query for workflow"))
    workflow = MultiAgentWorkflow()

    # Run with max iterations reached
    result = workflow.run(state)

    # Should have recorded routes
    assert len(result.route_history) > 0

    # Iteration should never exceed max
    from multi_agent_research_lab.core.config import get_settings

    settings = get_settings()
    assert result.iteration <= settings.max_iterations


def test_workflow_records_route_history() -> None:
    """Verify workflow records route history."""
    state = ResearchState(request=ResearchQuery(query="Test query for workflow"))
    workflow = MultiAgentWorkflow()
    result = workflow.run(state)

    assert len(result.route_history) >= 1
    # First route should be to researcher (no sources initially)
    assert result.route_history[0] == "researcher"


def test_workflow_supervisor_routes_correctly() -> None:
    """Verify supervisor routes through expected sequence."""
    state = ResearchState(request=ResearchQuery(query="Test query for workflow"))
    workflow = MultiAgentWorkflow()
    result = workflow.run(state)

    # First route should be to researcher (no sources)
    assert result.route_history[0] in ["researcher", "done"]

    # Should have multiple routes (supervisor loops until done or max iterations)
    assert len(result.route_history) >= 1


@patch("multi_agent_research_lab.agents.researcher.SearchClient")
@patch("multi_agent_research_lab.agents.analyst.LLMClient")
@patch("multi_agent_research_lab.agents.writer.LLMClient")
def test_workflow_captures_all_agent_results(
    mock_writer_llm: MagicMock,
    mock_analyst_llm: MagicMock,
    mock_search_class: MagicMock,
) -> None:
    """Verify all agent results are captured in the final state."""
    # Setup mocks
    mock_search = MagicMock()
    mock_search.search.return_value = [
        SourceDocument(title="Test", url="https://test.com", snippet="test")
    ]
    mock_search_class.return_value = mock_search

    mock_analyst_llm.return_value.complete.return_value = MagicMock(
        content="Analysis content", input_tokens=50, output_tokens=100, cost_usd=0.001
    )
    mock_writer_llm.return_value.complete.return_value = MagicMock(
        content="Final answer", input_tokens=50, output_tokens=100, cost_usd=0.001
    )

    state = ResearchState(request=ResearchQuery(query="Test query for results capture"))
    workflow = MultiAgentWorkflow()
    result = workflow.run(state)

    # Verify agent results contain all three agents
    agent_names = {r.agent for r in result.agent_results}
    assert AgentName.RESEARCHER in agent_names
    assert AgentName.ANALYST in agent_names
    assert AgentName.WRITER in agent_names


def test_workflow_trace_contains_agent_events() -> None:
    """Verify trace contains agent execution events."""
    with patch("multi_agent_research_lab.agents.researcher.SearchClient") as mock_search:
        mock_search.return_value.search.return_value = [
            SourceDocument(title="Test", url="https://test.com", snippet="test")
        ]

        with patch("multi_agent_research_lab.agents.analyst.LLMClient") as mock_analyst:
            mock_analyst.return_value.complete.return_value = MagicMock(
                content="Analysis content",
                input_tokens=50,
                output_tokens=100,
                cost_usd=0.001,
            )

            with patch("multi_agent_research_lab.agents.writer.LLMClient") as mock_writer:
                mock_writer.return_value.complete.return_value = MagicMock(
                    content="Final answer",
                    input_tokens=50,
                    output_tokens=100,
                    cost_usd=0.001,
                )

                state = ResearchState(
                    request=ResearchQuery(query="Test trace events"),
                )
                workflow = MultiAgentWorkflow()
                result = workflow.run(state)

                # Verify trace has events from agents
                assert len(result.trace) > 0

                # Each trace event should have name and payload
                for event in result.trace:
                    assert "name" in event
                    assert "payload" in event

                # Verify agent names are captured
                agent_names = [e["name"] for e in result.trace]
                assert any("researcher" in name for name in agent_names)


def test_workflow_iteration_count_respects_max() -> None:
    """Verify iteration count never exceeds max_iterations."""
    from multi_agent_research_lab.core.config import get_settings

    settings = get_settings()
    max_iters = settings.max_iterations

    state = ResearchState(request=ResearchQuery(query="Test iteration count"))
    workflow = MultiAgentWorkflow()
    result = workflow.run(state)

    # Critical invariant: iteration <= max_iterations
    assert result.iteration <= max_iters

    # Worker executions should be bounded by max_iterations
    worker_executions = [r for r in result.route_history if r != "done"]
    assert len(worker_executions) <= max_iters
