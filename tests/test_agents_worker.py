"""Unit tests for worker agents using mocks."""

from unittest.mock import MagicMock, patch

import pytest

from multi_agent_research_lab.agents.analyst import AnalystAgent
from multi_agent_research_lab.agents.researcher import ResearcherAgent
from multi_agent_research_lab.agents.writer import WriterAgent
from multi_agent_research_lab.core.schemas import AgentName, ResearchQuery, SourceDocument
from multi_agent_research_lab.core.state import ResearchState


def create_state(
    query: str = "Test query for research",
    sources: list[SourceDocument] | None = None,
    research_notes: str | None = None,
    analysis_notes: str | None = None,
    final_answer: str | None = None,
) -> ResearchState:
    """Create test state."""
    return ResearchState(
        request=ResearchQuery(query=query),
        sources=sources or [],
        research_notes=research_notes,
        analysis_notes=analysis_notes,
        final_answer=final_answer,
    )


class TestResearcherAgent:
    """Tests for ResearcherAgent."""

    @patch("multi_agent_research_lab.agents.researcher.SearchClient")
    def test_researcher_populates_sources_and_notes(self, mock_search_class: MagicMock) -> None:
        """Test that researcher populates sources and research_notes."""
        mock_client = MagicMock()
        mock_client.search.return_value = [
            SourceDocument(title="Test Source", snippet="Test content", url="https://example.com"),
        ]
        mock_search_class.return_value = mock_client

        state = create_state()
        agent = ResearcherAgent()
        result = agent.run(state)

        assert len(result.sources) == 1
        assert result.research_notes is not None
        assert "Test Source" in result.research_notes
        assert len(result.agent_results) == 1
        assert result.agent_results[0].agent == AgentName.RESEARCHER

    @patch("multi_agent_research_lab.agents.researcher.SearchClient")
    def test_researcher_handles_empty_search(self, mock_search_class: MagicMock) -> None:
        """Test that researcher handles empty search gracefully."""
        mock_client = MagicMock()
        mock_client.search.return_value = []
        mock_search_class.return_value = mock_client

        state = create_state()
        agent = ResearcherAgent()
        result = agent.run(state)

        assert len(result.sources) == 0
        assert result.research_notes is None
        assert len(result.errors) > 0
        assert "no results" in result.errors[0]

    @patch("multi_agent_research_lab.agents.researcher.SearchClient")
    def test_researcher_error_handling(self, mock_search_class: MagicMock) -> None:
        """Test that researcher raises exception on error (workflow handles it)."""
        mock_client = MagicMock()
        mock_client.search.side_effect = Exception("Search failed")
        mock_search_class.return_value = mock_client

        state = create_state()
        agent = ResearcherAgent()

        # Agent re-raises exception so workflow can handle it
        with pytest.raises(Exception, match="Search failed"):
            agent.run(state)


class TestAnalystAgent:
    """Tests for AnalystAgent."""

    @patch("multi_agent_research_lab.agents.analyst.LLMClient")
    def test_analyst_populates_analysis_notes(self, mock_llm_class: MagicMock) -> None:
        """Test that analyst populates analysis_notes."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content="Key findings: Test analysis content",
            input_tokens=100,
            output_tokens=200,
        )
        mock_llm_class.return_value = mock_llm

        state = create_state(
            sources=[SourceDocument(title="Source 1", snippet="Content 1")],
            research_notes="Research notes here",
        )
        agent = AnalystAgent()
        result = agent.run(state)

        assert result.analysis_notes is not None
        assert "Key findings" in result.analysis_notes
        assert len(result.agent_results) == 1
        assert result.agent_results[0].agent == AgentName.ANALYST

    def test_analyst_handles_missing_research_notes(self) -> None:
        """Test that analyst handles missing research notes gracefully."""
        state = create_state(sources=[SourceDocument(title="Source", snippet="Content")])
        agent = AnalystAgent()
        result = agent.run(state)

        assert result.analysis_notes is None
        assert len(result.errors) > 0
        assert "no research notes" in result.errors[0]

    def test_analyst_handles_missing_sources(self) -> None:
        """Test that analyst handles missing sources gracefully."""
        state = create_state(research_notes="Some notes but no sources")
        agent = AnalystAgent()
        result = agent.run(state)

        assert result.analysis_notes is None
        assert len(result.errors) > 0


class TestWriterAgent:
    """Tests for WriterAgent."""

    @patch("multi_agent_research_lab.agents.writer.LLMClient")
    def test_writer_populates_final_answer(self, mock_llm_class: MagicMock) -> None:
        """Test that writer populates final_answer."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content="Final answer: Test response",
            input_tokens=100,
            output_tokens=200,
        )
        mock_llm_class.return_value = mock_llm

        state = create_state(
            sources=[SourceDocument(title="Source", snippet="Content")],
            research_notes="Research notes",
            analysis_notes="Analysis notes",
        )
        agent = WriterAgent()
        result = agent.run(state)

        assert result.final_answer is not None
        assert "Final answer" in result.final_answer
        assert len(result.agent_results) == 1
        assert result.agent_results[0].agent == AgentName.WRITER

    def test_writer_handles_missing_research_notes(self) -> None:
        """Test that writer handles missing research notes gracefully."""
        state = create_state(sources=[SourceDocument(title="Source", snippet="Content")])
        agent = WriterAgent()
        result = agent.run(state)

        assert result.final_answer is None
        assert len(result.errors) > 0
        assert "no research notes" in result.errors[0]

    @patch("multi_agent_research_lab.agents.writer.LLMClient")
    def test_writer_without_analysis_notes(self, mock_llm_class: MagicMock) -> None:
        """Test that writer can still produce answer without analysis notes."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(
            content="Final answer without analysis",
            input_tokens=100,
            output_tokens=200,
        )
        mock_llm_class.return_value = mock_llm

        state = create_state(
            sources=[SourceDocument(title="Source", snippet="Content")],
            research_notes="Research notes only",
            analysis_notes=None,
        )
        agent = WriterAgent()
        result = agent.run(state)

        assert result.final_answer is not None
        assert len(result.errors) == 0
