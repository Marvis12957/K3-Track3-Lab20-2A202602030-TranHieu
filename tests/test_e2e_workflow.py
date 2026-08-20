"""End-to-end workflow tests using mocks."""

from unittest.mock import MagicMock, patch

import pytest

from multi_agent_research_lab.core.schemas import AgentName, ResearchQuery, SourceDocument
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.graph.workflow import MultiAgentWorkflow


@pytest.fixture
def mock_sources() -> list[SourceDocument]:
    """Create mock sources for testing."""
    return [
        SourceDocument(
            title="GraphRAG Overview",
            url="https://example.com/graphrag",
            snippet="A comprehensive overview of GraphRAG systems.",
        ),
        SourceDocument(
            title="Knowledge Graphs",
            url="https://example.com/kg",
            snippet="Introduction to knowledge graphs and their applications.",
        ),
    ]


class TestE2EWorkflow:
    """End-to-end workflow tests."""

    @patch("multi_agent_research_lab.agents.researcher.SearchClient")
    @patch("multi_agent_research_lab.agents.analyst.LLMClient")
    @patch("multi_agent_research_lab.agents.writer.LLMClient")
    def test_complete_workflow_with_mocks(
        self,
        mock_writer_llm: MagicMock,
        mock_analyst_llm: MagicMock,
        mock_search_class: MagicMock,
        mock_sources: list[SourceDocument],
    ) -> None:
        """Test complete workflow from query to final answer."""
        # Setup mock search
        mock_search = MagicMock()
        mock_search.search.return_value = mock_sources
        mock_search_class.return_value = mock_search

        # Setup mock LLM for analyst
        mock_analyst_llm.return_value.complete.return_value = MagicMock(
            content="Key findings from research: GraphRAG combines knowledge graphs "
            "with RAG for better contextual understanding.",
            input_tokens=100,
            output_tokens=200,
            cost_usd=0.001,
        )

        # Setup mock LLM for writer
        mock_writer_llm.return_value.complete.return_value = MagicMock(
            content="Based on research, GraphRAG is a novel approach that combines "
            "knowledge graphs with retrieval-augmented generation. Sources: "
            "GraphRAG Overview (example.com/graphrag) and Knowledge Graphs (example.com/kg).",
            input_tokens=150,
            output_tokens=300,
            cost_usd=0.002,
        )

        # Create initial state
        state = ResearchState(
            request=ResearchQuery(query="What is GraphRAG and how does it work?"),
        )

        # Run workflow
        workflow = MultiAgentWorkflow()
        result = workflow.run(state)

        # Verify sources populated
        assert len(result.sources) > 0, "Sources should be populated by researcher"
        assert result.research_notes is not None, "Research notes should be populated"

        # Verify analyst ran
        assert result.analysis_notes is not None, "Analysis notes should be populated"

        # Verify writer ran
        assert result.final_answer is not None, "Final answer should be populated"

        # Verify route history
        assert len(result.route_history) > 0, "Route history should be recorded"

        # Verify agent results captured
        agent_names = [r.agent for r in result.agent_results]
        assert AgentName.RESEARCHER in agent_names, "Researcher should have results"
        assert AgentName.ANALYST in agent_names, "Analyst should have results"
        assert AgentName.WRITER in agent_names, "Writer should have results"

        # Verify no errors (with mocks, everything should succeed)
        assert len(result.errors) == 0, f"No errors expected, got: {result.errors}"

    @patch("multi_agent_research_lab.agents.researcher.SearchClient")
    def test_workflow_with_empty_search(self, mock_search_class: MagicMock) -> None:
        """Test workflow handles empty search gracefully."""
        # Setup mock search to return empty
        mock_search = MagicMock()
        mock_search.search.return_value = []
        mock_search_class.return_value = mock_search

        state = ResearchState(
            request=ResearchQuery(query="What is GraphRAG?"),
        )

        workflow = MultiAgentWorkflow()
        result = workflow.run(state)

        # Should still record errors but workflow continues
        assert len(result.route_history) > 0

    def test_workflow_with_missing_prerequisites_for_analyst(self) -> None:
        """Test workflow handles analyst called without research notes."""
        state = ResearchState(
            request=ResearchQuery(query="Test query for analyst"),
            sources=[SourceDocument(title="Test", url="https://test.com", snippet="test")],
            # No research_notes - analyst should handle gracefully
        )

        workflow = MultiAgentWorkflow()
        result = workflow.run(state)

        # Workflow should continue despite analyst potentially failing
        assert len(result.route_history) > 0

    def test_workflow_iteration_enforcement(self) -> None:
        """Test that max iterations is enforced."""
        state = ResearchState(
            request=ResearchQuery(query="Test iteration enforcement"),
        )

        workflow = MultiAgentWorkflow()
        result = workflow.run(state)

        # With proper guards, iteration should never exceed max_iterations
        from multi_agent_research_lab.core.config import get_settings

        settings = get_settings()

        assert result.iteration <= settings.max_iterations, (
            f"Iteration {result.iteration} should not exceed max {settings.max_iterations}"
        )

    def test_workflow_route_sequence(self) -> None:
        """Test that workflow follows expected route sequence."""
        with patch("multi_agent_research_lab.agents.researcher.SearchClient") as mock_search:
            mock_search.return_value.search.return_value = [
                SourceDocument(title="Test", url="https://test.com", snippet="test")
            ]

            with (
                patch("multi_agent_research_lab.agents.analyst.LLMClient"),
                patch("multi_agent_research_lab.agents.writer.LLMClient"),
            ):
                state = ResearchState(
                    request=ResearchQuery(query="Test route sequence"),
                )

                workflow = MultiAgentWorkflow()
                result = workflow.run(state)

                # First route should be to researcher (no sources initially)
                assert result.route_history[0] == "researcher"

                # Routes should be in logical order: researcher -> analyst -> writer -> done
                routes = result.route_history
                if "analyst" in routes:
                    analyst_idx = routes.index("analyst")
                    if "researcher" in routes:
                        researcher_idx = routes.index("researcher")
                        assert researcher_idx < analyst_idx, "Researcher should come before analyst"

    def test_iteration_semantics_no_off_by_one(self) -> None:
        """Test that iteration never exceeds max_iterations."""
        from multi_agent_research_lab.core.config import get_settings

        settings = get_settings()
        max_iters = settings.max_iterations

        state = ResearchState(
            request=ResearchQuery(query="Test iteration semantics"),
        )

        workflow = MultiAgentWorkflow()
        result = workflow.run(state)

        # Key invariant: iteration count <= max_iterations
        assert result.iteration <= max_iters, (
            f"Iteration {result.iteration} exceeds max {max_iters}"
        )

        # route_history may have more entries (includes "done" entries)
        # but actual worker iterations should be bounded
        worker_routes = [r for r in result.route_history if r != "done"]
        assert len(worker_routes) <= max_iters, (
            f"Worker routes {len(worker_routes)} exceed max {max_iters}"
        )

    def test_workflow_terminates_when_done(self) -> None:
        """Test workflow properly terminates when all tasks complete."""
        # Pre-populate state so supervisor immediately sees all tasks done
        state = ResearchState(
            request=ResearchQuery(query="Test termination"),
            sources=[SourceDocument(title="Test", url="https://test.com", snippet="test")],
            research_notes="Some research notes",
            analysis_notes="Some analysis notes",
            final_answer="Some final answer",
        )

        workflow = MultiAgentWorkflow()
        result = workflow.run(state)

        # Should terminate quickly
        # First route should be "done" since all fields are populated
        assert result.route_history[0] == "done"
        # Iteration should not increase since we terminated immediately
        assert result.iteration == 0
