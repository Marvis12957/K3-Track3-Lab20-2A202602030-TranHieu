"""Benchmark for single-agent vs multi-agent comparison."""

import logging
import re
from collections.abc import Callable
from time import perf_counter

from multi_agent_research_lab.core.schemas import BenchmarkMetrics
from multi_agent_research_lab.core.state import ResearchState

logger = logging.getLogger(__name__)

Runner = Callable[[str], ResearchState]


def run_benchmark(
    run_name: str, query: str, runner: Runner
) -> tuple[ResearchState | None, BenchmarkMetrics]:
    """Run benchmark and collect metrics.

    Measures latency, cost, citation coverage, and failure rate.
    """
    started = perf_counter()
    state: ResearchState | None = None
    error_msg: str | None = None

    try:
        state = runner(query)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Benchmark runner failed")
        error_msg = str(exc)

    latency = perf_counter() - started

    # Calculate metrics
    failure_rate = _calculate_failure_rate(state, error_msg)
    estimated_cost = _calculate_cost(state)
    citation_coverage = _calculate_citation_coverage(state)

    # Determine status notes
    if error_msg:
        if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
            notes = f"External API quota/rate limit: {error_msg[:100]}"
        elif "timeout" in error_msg.lower():
            notes = f"Timeout: {error_msg[:100]}"
        else:
            notes = f"Error: {error_msg[:100]}"
    else:
        notes = "Completed"

    metrics = BenchmarkMetrics(
        run_name=run_name,
        latency_seconds=latency,
        estimated_cost_usd=estimated_cost,
        citation_coverage=citation_coverage,
        failure_rate=failure_rate,
        notes=notes,
    )

    return state, metrics


def _calculate_failure_rate(state: ResearchState | None, error_msg: str | None) -> float | None:
    """Calculate failure rate.

    Distinguishes between:
    - successful execution (0.0)
    - external API failure (captured in state.errors)
    - application failure (error_msg)
    """
    if error_msg:
        return 1.0

    if state is None:
        return 1.0

    # Check if workflow had errors
    if state.errors:
        # Check if errors are from external dependencies
        external_patterns = ["429", "RESOURCE_EXHAUSTED", "quota", "rate limit", "timeout"]
        for err in state.errors:
            for pattern in external_patterns:
                if pattern.lower() in err.lower():
                    return 1.0  # External failure
        # Internal errors
        return 1.0

    # Check if workflow completed successfully
    if state.final_answer:
        return 0.0

    # Partial completion
    return None


def _calculate_cost(state: ResearchState | None) -> float | None:
    """Aggregate cost from all agent results."""
    if state is None or not state.agent_results:
        return None

    total_cost = 0.0
    for result in state.agent_results:
        if result.metadata:
            cost = result.metadata.get("estimated_cost_usd")
            if cost:
                total_cost += cost

    return round(total_cost, 6) if total_cost > 0 else None


def _calculate_citation_coverage(state: ResearchState | None) -> float | None:
    """Calculate citation coverage.

    Heuristic: Count how many sources are referenced in the final answer.
    A source is considered "referenced" if its title or URL appears in the answer.

    Citation coverage = sources_referenced / total_sources
    """
    if state is None or not state.final_answer or not state.sources:
        return None

    answer_lower = state.final_answer.lower()
    referenced_count = 0

    for source in state.sources:
        # Check if source title or URL appears in answer
        title_lower = source.title.lower()
        url_lower = (source.url or "").lower()

        # Check for title, URL, or partial source references
        title_match = source.title[:20]
        title_in = title_lower in answer_lower
        url_in = url_lower in answer_lower
        ref_match = re.search(rf"\[\s*{title_match}", answer_lower, re.IGNORECASE)
        if title_in or url_in or ref_match:
            referenced_count += 1

    coverage = referenced_count / len(state.sources)
    return round(coverage, 2)


def aggregate_metrics(metrics_list: list[BenchmarkMetrics]) -> dict[str, float | None]:
    """Aggregate metrics across multiple benchmark runs."""
    total_latency = sum(m.latency_seconds for m in metrics_list)
    total_cost = sum(m.estimated_cost_usd or 0 for m in metrics_list)
    total_failures = sum(m.failure_rate or 0 for m in metrics_list)
    citations = [m.citation_coverage for m in metrics_list if m.citation_coverage is not None]
    total_citations = sum(citations) if citations else 0
    count = len(metrics_list)

    return {
        "avg_latency": round(total_latency / count, 2) if count > 0 else None,
        "avg_cost": round(total_cost, 6) if total_cost > 0 else None,
        "avg_failure_rate": round(total_failures / count, 2) if count > 0 else None,
        "avg_citation_coverage": round(total_citations / count, 2) if count > 0 else None,
    }
