# CLAUDE.md — Lab 20: Multi-Agent Research System

## 1. Project Context

- **Lab 20**: Multi-Agent Research System Starter
- **Mục tiêu**: Xây dựng hệ thống research multi-agent gồm Supervisor + Researcher + Analyst + Writer
- **Benchmark**: So sánh single-agent baseline với multi-agent workflow
- **Scope**: 2-hour educational lab
- **Students**: Implement TODO blocks để hoàn thành skeleton

## 2. Repository Architecture

**Implemented workflow**:

```
CLI
  ↓
Workflow (LangGraph)
  ↓
Supervisor (deterministic routing - NO LLM call)
  ↓
Researcher (search + research notes)
  ↓
Analyst (analysis notes)
  ↓
Writer (final answer)
  ↓
Output + Trace + Benchmark
```

**Current state**: All core components implemented and tested.

## 3. Repository Structure

| Directory | Responsibility |
|-----------|---------------|
| `agents/` | Agent implementations (supervisor, researcher, analyst, writer, critic) |
| `core/` | Config, schemas, state, errors |
| `graph/` | LangGraph workflow orchestration |
| `services/` | LLM client, search client, storage |
| `evaluation/` | Benchmark và report rendering |
| `observability/` | Logging, tracing hooks |
| `utils/` | Timer utilities |
| `tests/` | Unit tests |
| `docs/` | Lab guide, rubric, design template |

## 4. Agent Responsibilities

### Supervisor
- **Routing**: Deterministic decision based on shared state (NO LLM call for MVP)
- **Quyết định next agent**: researcher → analyst → writer → done
- **Enforce max iterations**: Stop if `iteration >= max_iterations`
- **Termination**: Check if `final_answer` exists
- **Không**: trực tiếp research, viết answer, gọi LLM cho routing

### Researcher
- **Input**: `state.request.query`, `state.request.max_sources`
- **Output**: `state.sources` (list[SourceDocument]), `state.research_notes` (str)
- **Tasks**: Search, filter sources, capture citations, create notes
- **Tools**: SearchClient

### Analyst
- **Input**: `state.research_notes`, `state.sources`
- **Output**: `state.analysis_notes` (str)
- **Tasks**: Extract claims, compare viewpoints, flag weak evidence
- **Tools**: LLMClient

### Writer
- **Input**: `state.research_notes`, `state.analysis_notes`, `state.sources`, `state.request.audience`
- **Output**: `state.final_answer` (str)
- **Tasks**: Synthesize response with citations
- **Tools**: LLMClient

### Critic
**OPTIONAL / BONUS** — Không phải core MVP.

## 5. Shared State

**File**: `core/state.py` — ResearchState (Pydantic BaseModel)

```
request: ResearchQuery
iteration: int
route_history: list[str]
sources: list[SourceDocument]
research_notes: str | None
analysis_notes: str | None
final_answer: str | None
agent_results: list[AgentResult]
trace: list[dict]
errors: list[str]
```

Methods:
- `record_route(route: str)` — appends to history, increments iteration
- `add_trace_event(name: str, payload: dict)` — adds trace event

**Note**: Không thêm `current_agent` nếu chưa có blocker thực tế. Có thể infer từ `route_history[-1]`.

## 6. LangGraph Rules

**MVP flow**:
```
START
  ↓
Supervisor
  ↓
Researcher
  ↓
Analyst
  ↓
Writer
  ↓
END
```

**Supervisor routing logic**:
```python
if state.iteration >= settings.max_iterations:
    return "done"
elif not state.sources:
    return "researcher"
elif not state.analysis_notes:
    return "analyst"
elif not state.final_answer:
    return "writer"
else:
    return "done"
```

- Ưu tiên simple linear flow
- Không over-engineer loop
- Termination = `final_answer` exists OR max iterations reached

## 7. Guardrails

**Bắt buộc**:
- `max_iterations`: Config value (default: 6)
- `timeout`: LLM calls phải có timeout
- `retry`: Exponential backoff cho transient failures
- `fallback/error handling`: Catch exceptions, log errors, continue gracefully
- `state validation`: Dùng Pydantic schemas
- **Không infinite loop**: Enforced by max_iterations

**Config values** (từ `core/config.py`):
```
MAX_ITERATIONS=6
TIMEOUT_SECONDS=60
```

**Không hard-code secrets**. Đọc từ config/settings.

## 8. LLM Rules

**Location**: `services/llm_client.py`

**Current**: Gemini client đã implement với:
- Retry (3 attempts, exponential backoff)
- Token usage tracking
- Cost estimation
- Logging

**Agent pattern**:
```python
llm = LLMClient()
response = llm.complete(system_prompt=..., user_prompt=...)
```

**LLMClient chịu trách nhiệm**:
- Provider API call
- Timeout handling
- Retry logic
- Token counting
- Cost estimation

**Agents KHÔNG tạo provider client riêng** trừ khi cần thiết.

## 9. Search Rules

**Location**: `services/search_client.py` — Skeleton, cần implement

**Pattern**: Researcher gọi SearchClient thay vì trực tiếp hard-code provider

**Implement options**:
- Tavily API
- Bing/SerpAPI
- Mock for development

## 10. Observability

**MVP trace_span** (từ `observability/tracing.py`):

```python
with trace_span("agent.researcher", {"iteration": 1}) as span:
    # do work
    span["output_length"] = len(result)
```

**MVP phải trace được**:
```
- agent name
- duration
- status (success/error)
- error message if any
```

**Không log**: API keys, secrets, credentials

**LangSmith/Langfuse**: Enhancement, không blocker cho core pipeline

## 11. Benchmark

**Goal**: Compare single-agent vs multi-agent trên cùng query

**MVP metrics**:
```
- latency (wall-clock time)
- estimated cost / token usage
- citation coverage (sources mentioned in answer / total sources)
- failure rate (errors / total runs)
```

**Quality score**: Có thể dùng rubric/manual evaluation

**Output**: `reports/benchmark_report.md` với markdown table

## 12. Testing

**Không xóa skeleton tests** chỉ để test pass.

**Sau implementation, bổ sung tests cho**:
- State validation
- Supervisor routing decisions
- Researcher output format
- Analyst output format
- Writer output format
- Max iteration enforcement
- Workflow termination
- CLI commands

**Pattern**: Unit tests dùng mock LLMClient/SearchClient

## 13. Coding Rules

1. **Inspect trước khi edit** — Đọc file, hiểu caller/dependency
2. **Minimal changes** — Chỉ sửa files thực sự cần
3. **Không refactor** unrelated code
4. **Giữ type hints** — Không bỏ type annotations
5. **Dùng Pydantic schemas** hiện có
6. **Không hard-code API keys**
7. **Không duplicate** existing abstractions
8. **Không over-engineer** — Simple > complex cho MVP
9. **Đọc config** từ settings, không đọc env vars trực tiếp trong agents

## 14. Scope Control

**Đây là educational lab — KHÔNG tự ý thêm**:
- Kafka, Redis, databases
- Microservices
- Kubernetes
- Event bus, message queue
- Distributed workers

**Chỉ thêm khi** task tương lai explicitly yêu cầu.

## 15. TODO Rules

```
TODO(student)
StudentTodoError
```

= Assignment work cho students.

**Không xóa TODOs** chỉ để "clean code". Chỉ xóa khi phần đó thực sự đã implement xong.

## 16. Implementation Workflow

Mỗi task:
```
Inspect → Understand → Plan → Modify minimal files → Test → Review diff → Report
```

## 17. Completion Report Format

Sau mỗi task:
```
Changed files:
...

Tests run:
...

Result:
...

Known issues:
...

Next step:
...
```

## 18. Priority

```
P0 (MUST HAVE) — All complete ✅
1. LLMClient           ✅ DONE
2. SearchClient        ✅ DONE
3. Researcher          ✅ DONE
4. Analyst             ✅ DONE
5. Writer              ✅ DONE
6. Supervisor          ✅ DONE
7. LangGraph workflow  ✅ DONE
8. Guardrails          ✅ DONE

P1 (SHOULD HAVE) — All complete ✅
- Tracing integration      ✅ DONE
- Benchmark implementation  ✅ DONE
- Unit tests               ✅ DONE (44 tests)

P2 (OPTIONAL/BONUS)
- Critic agent           ✅ Skeleton exists (optional)
- LangSmith/Langfuse     ⚠️ Optional enhancement
- Advanced quality eval  ⚠️ Manual rubric
- Report polish          ✅ Basic markdown report
```

## Current Implementation Status

| Component | Status |
|-----------|--------|
| LLMClient | ✅ Implemented (Gemini) |
| CLI baseline | ✅ Working |
| SearchClient | ✅ Implemented (Tavily + mock fallback) |
| Supervisor | ✅ Implemented (deterministic routing) |
| Researcher | ✅ Implemented |
| Analyst | ✅ Implemented |
| Writer | ✅ Implemented |
| LangGraph workflow | ✅ Implemented |
| Tracing | ✅ Integrated with trace events |
| Benchmark | ✅ Full implementation (latency, cost, citation, failure) |
| Tests | ✅ 44 tests passing |
| Iteration semantics | ✅ Fixed: iteration <= max_iterations |
| E2E test | ✅ Added with mocks |
