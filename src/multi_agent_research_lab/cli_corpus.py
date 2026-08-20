"""Offline corpus runner for multi-agent research benchmark.

Loads knowledge from offline JSON corpus and runs multi-agent workflow.
"""

import json
import logging
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.schemas import (
    AgentName,
    AgentResult,
    ResearchQuery,
    SourceDocument,
)
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.graph.workflow import MultiAgentWorkflow
from multi_agent_research_lab.observability.logging import configure_logging

logger = logging.getLogger(__name__)
console = Console()


def load_corpus(corpus_path: Path) -> list[dict[str, Any]]:
    """Load all topics from the corpus directory."""
    topics_dir = corpus_path / "topics"
    if not topics_dir.exists():
        raise FileNotFoundError(f"Topics directory not found: {topics_dir}")

    topics = []
    for json_file in sorted(topics_dir.glob("*.json")):
        with open(json_file) as f:
            data = json.load(f)
            topics.append(data)

    return topics


def extract_sources_from_topic(topic: dict[str, Any]) -> list[SourceDocument]:
    """Extract source documents from a topic's knowledge base."""
    sources = []
    kb = topic.get("knowledge_base", {})

    # Knowledge articles
    for article in kb.get("knowledge_articles", [])[:5]:
        sources.append(
            SourceDocument(
                title=article.get("title", "Untitled"),
                url=article.get("url"),
                snippet=article.get("summary", article.get("content", "")[:500]),
            )
        )

    # Source documents
    for doc in kb.get("source_documents", [])[:5]:
        sources.append(
            SourceDocument(
                title=doc.get("title", "Untitled"),
                url=doc.get("url"),
                snippet=doc.get("summary", doc.get("content", "")[:500]),
            )
        )

    return sources


def extract_research_task(topic: dict[str, Any]) -> str:
    """Extract the research task from a topic."""
    rt = topic.get("research_task", {})
    task = rt.get("task_description")
    if task:
        return str(task)
    question: str = topic.get("topic", {}).get("research_question", "") or ""
    return question if question else "Research query"


def generate_research_notes(query: str, sources: list[SourceDocument]) -> str:
    """Generate research notes from sources."""
    context_parts = []
    for i, source in enumerate(sources, 1):
        context_parts.append(f"[Source {i}] {source.title}\n{source.snippet}")

    context = "\n\n".join(context_parts)

    notes = f"""Research Query: {query}

Sources Found:
{context}

---
Research Notes:
Based on the sources above, the following key information relates to the query:
"""
    return notes


def run_corpus_topic(
    topic: dict[str, Any],
    sources: list[SourceDocument],
    task_description: str,
) -> ResearchState:
    """Run the workflow on a single topic with pre-loaded sources.

    Creates initial state with sources pre-populated (skipping web search)
    and research_notes pre-generated.
    """
    # Pre-populate research notes from corpus sources
    research_notes = generate_research_notes(task_description, sources)

    # Create initial state with sources already populated
    # This skips the Researcher's web search step
    state = ResearchState(
        request=ResearchQuery(query=task_description),
        sources=sources,
        research_notes=research_notes,
    )

    # Record researcher result (simulated since we skipped web search)
    state.agent_results.append(
        AgentResult(
            agent=AgentName.RESEARCHER,
            content=research_notes,
            metadata={"source_count": len(sources), "source": "offline_corpus"},
        )
    )

    # Run workflow (will go directly to Analyst since sources exist)
    workflow = MultiAgentWorkflow()
    result = workflow.run(state)

    return result


def run_corpus_benchmark(
    corpus_path: Path,
    topic_id: str | None = None,
    output_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Run multi-agent workflow on corpus topics.

    Args:
        corpus_path: Path to the corpus directory
        topic_id: Optional specific topic ID (e.g., "01")
        output_dir: Optional directory to save reports

    Returns:
        List of results with topic info and final state
    """
    settings = get_settings()
    configure_logging(settings.log_level)

    topics = load_corpus(corpus_path)

    # Filter by topic_id if specified
    if topic_id:
        topics = [
            t
            for t in topics
            if t.get("benchmark_metadata", {}).get("topic_id", "").endswith(topic_id)
        ]

    if not topics:
        console.print("[red]No topics found[/red]")
        return []

    results = []

    for topic in topics:
        topic_info = topic.get("benchmark_metadata", {})
        topic_name = topic.get("topic", {}).get("name", "Unknown")
        task_description = extract_research_task(topic)

        console.print(f"\n[cyan]Processing: {topic_name}[/cyan]")

        # Extract sources from knowledge base
        sources = extract_sources_from_topic(topic)

        if not sources:
            console.print("[yellow]  No sources found in topic[/yellow]")
            continue

        console.print(f"  [dim]Sources loaded: {len(sources)}[/dim]")

        # Run workflow with pre-loaded sources
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task("Running workflow...", total=None)
                result = run_corpus_topic(topic, sources, task_description)

            # Save report if output_dir specified
            if output_dir:
                output_dir.mkdir(parents=True, exist_ok=True)
                report_path = output_dir / f"{topic_info.get('topic_id', 'unknown')}_report.md"

                report_content = f"""# Research Report: {topic_name}

## Research Question
{task_description}

## Sources
"""
                for i, source in enumerate(result.sources, 1):
                    report_content += f"{i}. [{source.title}]({source.url or '#'})\n"
                    report_content += f"   {source.snippet[:200]}...\n\n"

                report_content += f"""
## Research Notes
{result.research_notes or "N/A"}

## Analysis Notes
{result.analysis_notes or "N/A"}

## Final Answer
{result.final_answer or "N/A"}

## Metrics
- Iterations: {result.iteration}
- Route History: {" → ".join(result.route_history)}
- Errors: {len(result.errors)}
"""

                report_path.write_text(report_content)
                console.print(f"  [green]Report saved: {report_path}[/green]")

            results.append(
                {
                    "topic_id": topic_info.get("topic_id"),
                    "topic_name": topic_name,
                    "num_sources": len(result.sources),
                    "has_final_answer": result.final_answer is not None,
                    "iteration": result.iteration,
                    "errors": result.errors,
                }
            )

        except Exception as exc:
            logger.exception(f"Failed on topic {topic_info.get('topic_id')}")
            console.print(f"  [red]Error: {exc}[/red]")
            results.append(
                {
                    "topic_id": topic_info.get("topic_id"),
                    "topic_name": topic_name,
                    "error": str(exc),
                }
            )

    return results


def main() -> None:
    """CLI entrypoint for corpus benchmark."""
    import sys

    corpus_path = Path("ai_agent_offline_research_corpus_v2")
    if not corpus_path.exists():
        corpus_path = Path(__file__).parent.parent.parent / "ai_agent_offline_research_corpus_v2"

    if len(sys.argv) > 1:
        topic_id = sys.argv[1]
        output_dir = Path("reports/corpus") if len(sys.argv) > 2 else None
    else:
        topic_id = None
        output_dir = Path("reports/corpus")

    results = run_corpus_benchmark(corpus_path, topic_id, output_dir)

    # Summary
    console.print("\n[bold]Summary[/bold]")
    console.print(f"Topics processed: {len(results)}")
    successful = sum(1 for r in results if r.get("has_final_answer"))
    console.print(f"Successful: {successful}")
    console.print(f"Failed: {len(results) - successful}")


if __name__ == "__main__":
    main()
