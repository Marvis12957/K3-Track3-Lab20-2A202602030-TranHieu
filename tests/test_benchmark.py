"""Tests for benchmark module."""

from multi_agent_research_lab.core.schemas import (
    AgentName,
    AgentResult,
    BenchmarkMetrics,
    ResearchQuery,
    SourceDocument,
)
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.evaluation.benchmark import (
    _calculate_citation_coverage,
    _calculate_cost,
    _calculate_failure_rate,
    aggregate_metrics,
    run_benchmark,
)


class MockRunner:
    """Mock runner for testing."""

    def __init__(
        self, state: ResearchState | None = None, exception: Exception | None = None
    ) -> None:
        self._state = state
        self._exception = exception

    def __call__(self, query: str) -> ResearchState:
        if self._exception:
            raise self._exception
        if self._state:
            return self._state
        return ResearchState(request=ResearchQuery(query=query))


def test_run_benchmark_success() -> None:
    """Test benchmark captures latency and metrics on success."""
    state = ResearchState(
        request=ResearchQuery(query="test query"),
        final_answer="Test answer",
        agent_results=[
            AgentResult(
                agent=AgentName.WRITER,
                content="test",
                metadata={"input_tokens": 100, "output_tokens": 200, "estimated_cost_usd": 0.001},
            )
        ],
    )
    runner = MockRunner(state)
    result_state, metrics = run_benchmark("test", "test query", runner)

    assert metrics.run_name == "test"
    assert metrics.latency_seconds > 0
    assert metrics.failure_rate == 0.0
    assert result_state is not None
    assert result_state.final_answer == "Test answer"


def test_run_benchmark_failure() -> None:
    """Test benchmark captures failure when runner raises exception."""
    runner = MockRunner(exception=Exception("API error"))
    _state, metrics = run_benchmark("test", "query", runner)

    assert metrics.failure_rate == 1.0
    assert "Error" in metrics.notes


def test_run_benchmark_quota_failure() -> None:
    """Test benchmark captures quota/rate-limit failures."""
    runner = MockRunner(exception=Exception("429 RESOURCE_EXHAUSTED"))
    _state, metrics = run_benchmark("test", "query", runner)

    assert metrics.failure_rate == 1.0
    assert "quota" in metrics.notes.lower() or "rate limit" in metrics.notes.lower()


def test_calculate_failure_rate_with_final_answer() -> None:
    """Test failure rate is 0 when final answer exists."""
    state = ResearchState(request=ResearchQuery(query="test query"))
    state.final_answer = "Some answer"

    rate = _calculate_failure_rate(state, None)
    assert rate == 0.0


def test_calculate_failure_rate_with_errors() -> None:
    """Test failure rate is 1 when errors exist."""
    state = ResearchState(request=ResearchQuery(query="test query"))
    state.errors.append("Something went wrong")

    rate = _calculate_failure_rate(state, None)
    assert rate == 1.0


def test_calculate_failure_rate_external() -> None:
    """Test failure rate is 1 for external API errors."""
    state = ResearchState(request=ResearchQuery(query="test query"))
    state.errors.append("429 RESOURCE_EXHAUSTED")

    rate = _calculate_failure_rate(state, None)
    assert rate == 1.0


def test_calculate_cost_with_metadata() -> None:
    """Test cost calculation from agent results."""
    state = ResearchState(request=ResearchQuery(query="test query"))
    state.agent_results = [
        AgentResult(
            agent=AgentName.RESEARCHER,
            content="test",
            metadata={"estimated_cost_usd": 0.001},
        ),
        AgentResult(
            agent=AgentName.ANALYST,
            content="test",
            metadata={"estimated_cost_usd": 0.002},
        ),
    ]

    cost = _calculate_cost(state)
    assert cost is not None
    assert cost == 0.003


def test_calculate_cost_no_results() -> None:
    """Test cost is None when no agent results."""
    state = ResearchState(request=ResearchQuery(query="test query"))

    cost = _calculate_cost(state)
    assert cost is None


def test_calculate_citation_coverage() -> None:
    """Test citation coverage calculation."""
    state = ResearchState(
        request=ResearchQuery(query="test query"),
        final_answer="Based on Source Title and example.com, we find...",
        sources=[
            SourceDocument(title="Source Title", url="https://example.com", snippet="content"),
            SourceDocument(title="Other Source", url="https://other.com", snippet="content"),
        ],
    )

    coverage = _calculate_citation_coverage(state)
    assert coverage is not None
    assert coverage == 0.5  # Only 1 of 2 sources referenced


def test_calculate_citation_coverage_no_sources() -> None:
    """Test citation coverage is None when no sources."""
    state = ResearchState(request=ResearchQuery(query="test query"))
    state.final_answer = "Some answer"

    coverage = _calculate_citation_coverage(state)
    assert coverage is None


def test_aggregate_metrics() -> None:
    """Test aggregation of multiple benchmark runs."""
    metrics = [
        BenchmarkMetrics(run_name="run1", latency_seconds=1.0, citation_coverage=0.5),
        BenchmarkMetrics(run_name="run2", latency_seconds=2.0, citation_coverage=1.0),
    ]

    result = aggregate_metrics(metrics)

    assert result["avg_latency"] == 1.5
    assert result["avg_citation_coverage"] == 0.75
