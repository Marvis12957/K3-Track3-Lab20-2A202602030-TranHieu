# Design Template

## Problem

Build a multi-agent research assistant that accepts a research query, searches the web, analyzes findings, and produces a well-cited final answer.

## Why multi-agent?

Single-agent approaches mix concerns: research, analysis, and writing compete for context window space and attention. Multi-agent separates these concerns:

- **Researcher**: Focused on search and source gathering
- **Analyst**: Extracts key findings from research
- **Writer**: Synthesizes into final answer with citations

## Agent roles

| Agent | Responsibility | Input | Output | Failure mode |
|---|---|---|---|---|
| Supervisor | Route to next agent, enforce max iterations | Current state | Route decision | None (deterministic) |
| Researcher | Search web, gather sources | query, max_sources | sources[], research_notes | Empty results → error |
| Analyst | Extract key findings | sources, research_notes | analysis_notes | Missing prerequisites → graceful skip |
| Writer | Synthesize final answer | all prior outputs | final_answer | Missing prerequisites → graceful skip |

## Shared state

```python
ResearchState:
  - request: ResearchQuery       # User input
  - iteration: int              # Worker execution count
  - route_history: list[str]     # Routing decisions
  - sources: list[SourceDocument]  # Gathered sources
  - research_notes: str | None   # Research findings
  - analysis_notes: str | None   # Analysis output
  - final_answer: str | None     # Final response
  - agent_results: list[AgentResult]  # Per-agent metrics
  - trace: list[dict]            # Execution trace
  - errors: list[str]             # Error messages
```

## Routing policy

```
START
  ↓
Supervisor
  ↓
[no sources?] → Researcher → Supervisor
  ↓
[no analysis?] → Analyst → Supervisor
  ↓
[no answer?] → Writer → Supervisor
  ↓
[done]
```

Supervisor routing logic:
1. If iteration >= max_iterations → done
2. If no sources → researcher
3. If no analysis_notes → analyst
4. If no final_answer → writer
5. Otherwise → done

## Guardrails

- **Max iterations**: 6 (prevents infinite loops)
- **Timeout**: 60s per LLM call
- **Retry**: 3 attempts with exponential backoff
- **Fallback**: Graceful degradation on errors
- **Validation**: Pydantic schemas for all inputs/outputs

## Benchmark plan

### Queries
- "What is GraphRAG and how does it work?"
- "Compare RAG vs fine-tuning approaches"

### Metrics
- Latency (wall-clock time)
- Estimated cost (token usage)
- Citation coverage (sources referenced / total sources)
- Failure rate (errors / total runs)

### Expected outcome
Multi-agent should show better citation coverage at the cost of higher latency and cost.
