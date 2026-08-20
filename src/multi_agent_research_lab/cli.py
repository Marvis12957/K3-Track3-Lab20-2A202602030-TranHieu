"""Command-line entrypoint for the lab starter."""

import logging
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.errors import StudentTodoError
from multi_agent_research_lab.core.schemas import ResearchQuery
from multi_agent_research_lab.core.state import ResearchState
from multi_agent_research_lab.evaluation.benchmark import run_benchmark
from multi_agent_research_lab.evaluation.report import render_markdown_report
from multi_agent_research_lab.graph.workflow import MultiAgentWorkflow
from multi_agent_research_lab.observability.logging import configure_logging
from multi_agent_research_lab.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

app = typer.Typer(help="Multi-Agent Research Lab starter CLI")
console = Console()


def _init() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)


def _parse_query(query: str) -> ResearchQuery:
    try:
        return ResearchQuery(query=query)
    except ValidationError as exc:
        console.print(
            Panel.fit(
                f"Invalid query: {exc.errors()[0]['msg']}",
                title="Input Error",
                style="red",
            )
        )
        raise typer.Exit(code=1) from exc


@app.command()
def baseline(
    query: Annotated[str, typer.Option("--query", "-q", help="Research query")],
) -> None:
    """Run a minimal single-agent baseline with LLM."""

    _init()
    request = _parse_query(query)
    state = ResearchState(request=request)

    try:
        llm = LLMClient()

        system_prompt = (
            "You are a research assistant. Answer the user's question concisely and accurately. "
            "Include relevant information and cite sources when possible."
        )
        user_prompt = f"Query: {request.query}\n\nPlease provide a comprehensive research summary."

        response = llm.complete(system_prompt=system_prompt, user_prompt=user_prompt)

        state.final_answer = response.content

        # Display metrics table
        table = Table(title="Single-Agent Baseline Metrics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Input Tokens", str(response.input_tokens or "N/A"))
        table.add_row("Output Tokens", str(response.output_tokens or "N/A"))
        cost_str = f"${response.cost_usd:.6f}" if response.cost_usd else "N/A"
        table.add_row("Est. Cost (USD)", cost_str)

        console.print(Panel.fit(state.final_answer, title="Single-Agent Baseline"))
        console.print(table)

    except Exception as exc:  # noqa: BLE001
        logger.exception("Baseline failed")
        console.print(Panel.fit(f"Error: {exc}", title="Baseline Error", style="red"))
        raise typer.Exit(code=1) from exc


@app.command("multi-agent")
def multi_agent(
    query: Annotated[str, typer.Option("--query", "-q", help="Research query")],
) -> None:
    """Run the multi-agent workflow skeleton."""

    _init()
    state = ResearchState(request=_parse_query(query))
    workflow = MultiAgentWorkflow()
    try:
        result = workflow.run(state)
    except StudentTodoError as exc:
        console.print(Panel.fit(str(exc), title="Expected TODO", style="yellow"))
        raise typer.Exit(code=2) from exc
    console.print(result.model_dump_json(indent=2))


@app.command()
def benchmark(
    query: Annotated[str, typer.Option("--query", "-q", help="Research query")],
    output: Annotated[str | None, typer.Option("--output", "-o", help="Output file path")] = None,
) -> None:
    """Run benchmark comparing single-agent vs multi-agent."""

    _init()
    request = _parse_query(query)

    console.print(Panel.fit(f"Running benchmark for query: {request.query}", title="Benchmark"))

    # Runner functions
    def single_agent_runner(q: str) -> ResearchState:
        state = ResearchState(request=ResearchQuery(query=q))
        llm = LLMClient()
        response = llm.complete(
            system_prompt="You are a research assistant. Answer concisely and accurately.",
            user_prompt=f"Query: {q}\n\nProvide a comprehensive research summary.",
        )
        state.final_answer = response.content
        return state

    def multi_agent_runner(q: str) -> ResearchState:
        state = ResearchState(request=ResearchQuery(query=q))
        workflow = MultiAgentWorkflow()
        return workflow.run(state)

    # Run single-agent
    console.print("[cyan]Running Single-Agent baseline...[/cyan]")
    single_state = None
    try:
        single_state = single_agent_runner(request.query)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Single-agent failed: %s", exc)
        single_state = None

    _, single_metrics = run_benchmark("Single-Agent", request.query, single_agent_runner)

    # Run multi-agent
    console.print("[cyan]Running Multi-Agent workflow...[/cyan]")
    multi_state = None
    try:
        multi_state = multi_agent_runner(request.query)
    except StudentTodoError as exc:
        console.print(Panel.fit(str(exc), title="Expected TODO", style="yellow"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Multi-agent failed: %s", exc)
        multi_state = None

    _, multi_metrics = run_benchmark("Multi-Agent", request.query, multi_agent_runner)

    # Generate report
    report = render_markdown_report(
        metrics=[single_metrics, multi_metrics],
        query=request.query,
        single_state=single_state,
        multi_state=multi_state,
    )

    # Save or print report
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report)
        console.print(f"[green]Report saved to: {output_path}[/green]")
    else:
        console.print(report)

    console.print("[green]Benchmark complete![/green]")


if __name__ == "__main__":
    app()
