# Multi-agent estimation graph (Session 13 / feature-066)

Living technical reference for the **LangGraph multi-agent estimation graph** in
`master-ia`. This path is **additive**: it does not replace the fixed RAG pipeline
(`POST /api/v1/estimate/rag`), CAG v1/v2, or the Session 12 agent
(`POST /api/v1/estimate/agent`).

**Work item:** [feature-066-langgraph-multi-agent-estimation-s13.md](../work-items/feature-066-langgraph-multi-agent-estimation-s13.md)  
**Session note:** [learnings/docs/sesiones/sesion-13-langgraph-multi-agent-estimation.md](../../learnings/docs/sesiones/sesion-13-langgraph-multi-agent-estimation.md)  
**Official reference:** `ai-engineering` branch `session_13_live`
(`estimator/app/domain/graph/*`)

**Draft status:** Step 7 (CLI + exercises) landed with this note. Step 5 (Postgres
checkpointer + lifespan) and Step 6 (HTTP router) may land in parallel on the same
branch — treat lifespan/HTTP sections as the target contract until those steps mark
themselves done in the work item.

---

## Purpose

Show that a multi-step estimation flow with human review is an **explicit, typed
graph** — not a black-box framework — while keeping the external contract
“transcript in → structured estimate (+ status) out”.

Pedagogical beats:

1. **Handovers** with `Command(goto=…, update=…)`.
2. **Human gates** with `interrupt()` + `Command(resume=…)`.
3. **Send fan-out** per approved task + keyed reducer (`merge_task_hours`).
4. **Agentic recovery** of doubtful hours at the join node.
5. Optional **commercial proposal** when gate 2 asks for it.

---

## Topology

```text
START → classifier_agent
        ──Command(goto)──▶ structure_agent
        ──edge──▶ human_gate_structure (interrupt #1: structure_review)
        ──Send fan-out──▶ estimate_task_hours × N
        ──edge──▶ recover_and_handover (join + optional recovery agent)
        ──Command(goto)──▶ analysis_agent
        ──edge──▶ human_gate_analysis (interrupt #2: final_review)
        ──conditional──▶ proposal_agent | END
```

---

## Surfaces

| Surface | Path / command | Status |
| --- | --- | --- |
| Library | `build_graph(checkpointer)` | Done (MemorySaver e2e tested) |
| CLI | `uv run python app/scripts/run_graph_s13.py [--memory] [--stub]` | Done (Step 7) |
| Exercise kit | `exercises/session-13/` | Done (Step 7) |
| FastAPI lifespan → `app.state.graph` | `app/main.py` | Step 5 (parallel track) |
| HTTP API | `POST /api/v1/estimate/graph*` | *(pending Step 6)* |
| Stream / progress / proposal-on-demand | optional Step 8 | Pending |
| React wizard | optional child front feature | Pending |

---

## Module map

```text
app/services/estimation_graph/
├── state.py           # EstimationState, merge_task_hours (keyed reducer)
├── build.py           # build_graph, fan_out_hours, route_after_gate2
├── checkpointer.py    # saver_conninfo + open_checkpointer (Step 5)
├── structured.py      # complete_graph_structured (Instructor/LiteLLM)
├── schemas.py         # ComplexityClassification, ReliabilityReport, …
├── personas.py        # Optional persona prefixes behind GRAPH_PERSONAS_ENABLED
└── agents/
    ├── classifier.py
    ├── structure.py   # wraps run_structure_agent
    ├── gates.py       # interrupt() gates
    ├── hours.py       # estimate_one seam + recover_and_handover
    ├── analysis.py
    └── proposal.py

app/scripts/run_graph_s13.py
exercises/session-13/
tests/estimation_graph/
```

Package home is **`app/services/estimation_graph/`** (not a new `app/domain/` tree).

---

## Deliberate fork decisions

| Topic | `master-ia` choice | Official `session_13_live` |
| --- | --- | --- |
| Package layout | `app/services/estimation_graph/` | `estimator/app/domain/graph/` |
| Logging | stdlib `logging` + `extra={}` | `structlog` |
| Structured LLM | `complete_structured` / `complete_graph_structured` | `LLMWrapper` |
| Structure / recovery agents | Raw `AsyncOpenAI().responses.*` (same as feature-054) | Same Responses exception |
| HTTP prefix | `/api/v1/estimate/graph*` *(Step 6)* | `/v1/estimate/graph*` |
| UI | React `web/` (optional child) | Rails `estimator-web` |

Do **not** port `structlog` or Rails. Do **not** replace existing estimate agent / RAG / CAG routes.

---

## CLI

```bash
# Partial offline: MemorySaver + stub hours (needs OPENAI_API_KEY for LLM agents)
uv run python app/scripts/run_graph_s13.py --memory --stub

# Full path (Postgres checkpointer + real task-hours) — needs Step 5 + corpus
uv run python app/scripts/run_graph_s13.py \
  --out exercises/session-13/example_run_complex.txt
```

Behaviour:

- Auto-approves gate 1 (`structure_review`: `{approved: true}`).
- Auto-approves gate 2 (`final_review`: `{validated: true, want_proposal: true}`).
- `--stub` monkeypatches `agents.hours.estimate_one` with deterministic grounded hours.
- Without `--memory`, the CLI calls `open_checkpointer()` from `checkpointer.py`
  (Step 5). If that helper is missing, the CLI exits with a clear error and asks
  for `--memory`.

Do not commit generated `*_run*.txt` / `example_run_*.txt` under exercises.

---

## Checkpointer (Step 5)

Target / implemented behaviour (official parity):

- Production: `AsyncPostgresSaver` over project Postgres with `AsyncConnectionPool`
  (survive long human pauses).
- `DATABASE_URL` driver stripping: `postgresql+asyncpg://` → `postgresql://`
  (`saver_conninfo`).
- `await checkpointer.setup()` on startup (idempotent; creates `checkpoints*`).
- Graph init failure → `app.state.graph = None`; other routers keep serving;
  graph routes return **503** once Step 6 exists.

---

## HTTP contract *(pending Step 6)*

| Verb | Path | Behaviour |
| --- | --- | --- |
| POST | `/api/v1/estimate/graph` | Start → pause at gate 1 or complete |
| POST | `/api/v1/estimate/graph/{id}/resume` | Resume; 409 if nothing pending |
| GET | `/api/v1/estimate/graph/{id}/state` | Snapshot; 404 unknown |

Auth: reuse `ESTIMATE_API_KEY`. Rate limits aligned with estimate routes.

---

## Settings

Documented in `.env.example`:

```text
GRAPH_EXTRACTION_MODEL=gpt-4o-mini
GRAPH_GENERATION_MODEL=gpt-4o
GRAPH_CLASSIFIER_MODEL=gpt-4o-mini
GRAPH_ANALYSIS_MODEL=gpt-4o
GRAPH_PROPOSAL_MODEL=gpt-4o
GRAPH_PROPOSAL_ENABLED=true
GRAPH_PERSONAS_ENABLED=true
GRAPH_STRUCTURE_EFFORT_BY_COMPLEXITY={"low":"low","medium":"medium","high":"high"}
```

Structure / recovery Responses calls reuse `AGENT_MODEL`, `AGENT_REASONING_EFFORT`,
`AGENT_MAX_ITERATIONS`.

---

## Tests

```bash
uv run pytest tests/estimation_graph tests/exercises/test_session_13_assets.py -q
```

Default suite: MemorySaver + faked `complete_graph_structured` + faked
`run_structure_agent` / `estimate_one` — no API keys, no Postgres.

CLI helpers covered in `tests/estimation_graph/test_cli_helpers.py` (render, stub
hours, auto-approve `run_to_completion`).

---

## Related

- Session 12 agent: [agentic-estimation-loop.md](./agentic-estimation-loop.md)
- Work item: [feature-066](../work-items/feature-066-langgraph-multi-agent-estimation-s13.md)
- Exercise runbook: [exercises/session-13/README.md](../../exercises/session-13/README.md)
