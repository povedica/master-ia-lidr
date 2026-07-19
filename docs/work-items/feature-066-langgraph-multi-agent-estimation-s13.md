# Feature: LangGraph Multi-Agent Estimation (Session 13)

## Objective

Bring `master-ia` to **Session 13 live parity** with the official Master IA repo
(`/Users/pablo.poveda/CodeProjects/ai-engineering`, branch `session_13_live`):

1. Evolve the Session 12 agentic package from the current **single autonomous loop**
   into the official **two-phase** shape (`run_structure_agent` +
   `run_task_hours_recovery_agent`) that Session 13 reuses.
2. Port the **multi-agent LangGraph estimation graph** with explicit handovers,
   `Send` fan-out, keyed reducers, two human `interrupt()` gates, and Postgres
   checkpointer.
3. Expose the graph over HTTP (`start` / `resume` / `state`, plus optional stream
   progress) and a CLI deliverable (`run_graph_s13.py`), adapted to `master-ia`
   layout and conventions.

**Pedagogical goal:** show that a multi-step estimation flow with human review is an
explicit, typed graph — not a black-box framework — while keeping the external
contract “transcript in → structured estimate (+ status) out”.

### Comparison snapshot (2026-07-19)

| Repo | Branch | Role |
| --- | --- | --- |
| `master-ia` | current student fork | Has S05–S11 parity (feature-053 child slices), S12 single-loop agent (`feature-054`) |
| `ai-engineering` | `session_13_live` | Official master; S13 multi-agent graph + evolved S12 two-phase agents |

**Layout difference (non-goal to replicate verbatim):** official code lives under
`estimator/app/{domain/graph,generation/agentic,api/routers}`; `master-ia` keeps
`app/{services,routers}` (+ new `app/services/estimation_graph/` or
`app/domain/graph/` — choose one at implementation; this spec uses
`app/services/estimation_graph/`).

---

## Context

### What `master-ia` already has (do not rebuild)

| Area | Status | Relevance to S13 |
| --- | --- | --- |
| RAG stages / task hours | `POST /api/v1/estimate/rag/stages/*`, `rag_task_hours.estimate_one_task` | Fan-out hours node wraps this |
| Agentic S12 (simple loop) | `app/services/agentic/agent_loop.py` → `run_estimation_agent` | **Outdated shape** vs official; must evolve |
| Agent HTTP | `POST /api/v1/estimate/agent` | Keep additive; graph is a new surface |
| Observability | Logfire + Langfuse adapters | Prefer Logfire spans per node (already in stack); no `structlog` |
| Postgres + pgvector | `DATABASE_URL` (`postgresql+asyncpg://…`) | Checkpointer reuses same DB with plain libpq DSN |
| API hardening | `ESTIMATE_API_KEY`, rate limit, `X-Request-ID` | Reuse on graph routes |
| Parity roadmap S05–S11 | `feature-053` (closed) | S13 is the **next session track**, not a reopen of 053 |

### Official Session 13 materials (source of truth)

| Artifact | Official path | Purpose |
| --- | --- | --- |
| Graph package | `estimator/app/domain/graph/` | State, build, checkpointer, agents, gates, activity |
| Pre-exercise nodes | `domain/graph/nodes.py` | Sequential 5-node “before”; keep for teaching, not wired in live build |
| Live agents | `domain/graph/agents/*` | classifier, structure, gates, hours, analysis, proposal |
| HTTP contract | `api/routers/estimate_graph.py` | start / resume / state + stream / progress / proposal |
| Schemas | `domain/schemas/graph_estimation.py` | Public API models |
| CLI | `scripts/run_graph_s13.py` | Auto-approve gates; `--memory` / `--stub` |
| Exercise assets | `exercises/session-13/*` | Sample transcripts + README |
| Tests | `tests/domain/graph/` | MemorySaver + faked LLM/retrieval |
| Deps | `langgraph`, `langgraph-checkpoint-postgres`, `psycopg[binary]`, `psycopg_pool` | Required |

### Live graph topology (must match behavior)

```text
START → classifier_agent
        ──Command(goto)──▶ structure_agent
        ──edge──▶ human_gate_structure (interrupt #1)
        ──Send fan-out──▶ estimate_task_hours × N
        ──edge──▶ recover_and_handover (join + optional recovery agent)
        ──Command(goto)──▶ analysis_agent
        ──edge──▶ human_gate_analysis (interrupt #2)
        ──conditional──▶ proposal_agent | END
```

### Deliberate fork decisions (do not “fix” without ADR)

1. **No `structlog`** — use stdlib `logging` + `extra={}` with stable keys
   (`graph_ready`, `graph_estimate_failed`, `agent_classifier_done`, …).
2. **Structured LLM path** — classifier / analysis / proposal use
   `complete_structured` (Instructor + LiteLLM), not official `LLMWrapper`.
3. **Responses API exception preserved** — `run_structure_agent` and
   `run_task_hours_recovery_agent` keep raw `AsyncOpenAI().responses.*` (same
   exception as `feature-054`).
4. **Prefix** — expose under `/api/v1/estimate/graph*` (not bare `/v1/...`).
5. **UI** — React `web/` for optional wizard / activity panel; do **not** port Rails
   `estimator-web`.
6. **Package home** — prefer `app/services/estimation_graph/` (services layer) over
   inventing a full `app/domain/` tree; if a thin `app/domain/graph/` is clearer for
   teaching, document the choice in the implementation note — one package only.
7. **Keep fork advantages** — Langfuse, retrieval-debug, `/api/v2/estimate`,
   semantic cache, `LLMPipeline` guardrails remain untouched.
8. **Do not replace** `POST /api/v1/estimate/agent` or `RagEstimationService`.

### Parent / sibling work

| Work item | Relationship |
| --- | --- |
| `feature-053-official-master-parity-alignment.md` | Closed S05–S11 program; residual FR-20 / corpus jobs stay deferred |
| `feature-054-agentic-estimation-loop.md` | S12 baseline; this feature **extends** agentic APIs for S13 |
| Residual 053 gaps (named StageConfig eval, corpus index jobs, 7 chunkers, Rails UI) | **Out of scope** here |

---

## Scope

### Includes

**Phase A — S12 agent evolution (prerequisite for S13 nodes)**

- Port / adapt official two-phase agent APIs into `app/services/agentic/`:
  - `run_structure_agent(brief, …) → (AgentStructure, AgentTrace)`
  - `run_task_hours_recovery_agent(flagged_tasks, …) → AgentTaskHoursRun`
  - Tool schemas needed by recovery (`search_budgets` reformulation +
    `derive_task_hours` / consensus injection), matching official semantics
- Keep existing `run_estimation_agent` **or** deprecate behind a thin wrapper that
  documents the pedagogical shift (prefer keep for CLI/HTTP backward compat until
  a follow-up removes it)
- Unit tests with mocked Responses client (fast suite)

**Phase B — LangGraph multi-agent core**

- Dependencies: `langgraph`, `langgraph-checkpoint-postgres`, `psycopg[binary]`
  (+ pool usage as in official `AsyncConnectionPool`)
- Package `app/services/estimation_graph/` (or chosen equivalent):
  - `state.py` — `EstimationState`, `merge_task_hours` keyed reducer
  - `build.py` — `build_graph`, `fan_out_hours`, `route_after_gate2`
  - `checkpointer.py` — `saver_conninfo` + `open_checkpointer` (strip `+asyncpg`)
  - `observability.py` — Logfire span helper (no-op without token)
  - `personas.py` — optional persona prefixes behind flag
  - `schemas.py` — internal LLM models (`ComplexityClassification`,
    `ReliabilityReport`, `CommercialProposal`, …)
  - `activity.py` — didactic activity feed for stream mode
  - `agents/*` — classifier, structure, gates, hours, analysis, proposal
  - Optional keep of sequential `nodes.py` for teaching contrast (not wired)
- Wire graph into FastAPI `lifespan` → `app.state.graph`; failure → `graph=None`
  (503 on graph routes only)

**Phase C — HTTP + CLI + exercises**

- Router `app/routers/estimate_graph.py` under `/api/v1/estimate`:
  - `POST /graph` — start until first gate
  - `POST /graph/{estimation_id}/resume` — human decision; 409 if not paused
  - `GET /graph/{estimation_id}/state` — snapshot
  - Optional (same PR or baby-step follow-up): `POST /graph/stream`,
    `POST /graph/{id}/resume-stream`, `GET /graph/{id}/progress`,
    `POST /graph/{id}/proposal`
- Public schemas in `app/schemas/graph_estimation.py`
- CLI `app/scripts/run_graph_s13.py` (`--memory`, `--stub`, `--out`)
- Exercise assets `exercises/session-13/` (transcripts + README adapted to
  `master-ia` commands)
- Settings + `.env.example` + README + technical doc + Second Brain session note

**Phase D (optional, can be a child front feature)**

- React wizard: start → review structure → resume → review estimate → optional
  proposal; poll progress when stream endpoints exist

### Excludes

- Porting Rails `estimator-web` graph wizard
- Replacing `/api/v1/estimate/rag` or CAG v1/v2 paths
- Reopening feature-053 residual items (FR-20 StageConfig scoreboard, corpus index
  async jobs, full 7 chunking strategies, tier resolver)
- Migrating the whole codebase to LangGraph
- Adding `structlog`
- Committing generated run artifacts under `exercises/session-13/*_run*.txt` or
  `evaluation/**/results/`
- IVFFlat / halfvec / S08 antipattern scripts

---

## Functional Requirements

### FR-01 — Dependencies and settings

Add (names may be snake_case in `Settings`):

```text
# Session 13 — estimation graph
GRAPH_EXTRACTION_MODEL=gpt-4o-mini          # legacy sequential nodes if kept
GRAPH_GENERATION_MODEL=gpt-4o
GRAPH_CLASSIFIER_MODEL=gpt-4o-mini
GRAPH_ANALYSIS_MODEL=gpt-4o
GRAPH_PROPOSAL_MODEL=gpt-4o
GRAPH_PROPOSAL_ENABLED=true
GRAPH_PERSONAS_ENABLED=true
# JSON or documented mapping: low/medium/high → reasoning effort
GRAPH_STRUCTURE_EFFORT_BY_COMPLEXITY={"low":"low","medium":"medium","high":"high"}
```

Reuse existing agent settings (`AGENT_MODEL`, `AGENT_REASONING_EFFORT`, …) for
structure / recovery Responses calls.

### FR-02 — Checkpointer

- Production/default: `AsyncPostgresSaver` over project Postgres with connection
  pool (survive long human pauses).
- `DATABASE_URL` driver stripping: `postgresql+asyncpg://` → `postgresql://`.
- `await checkpointer.setup()` on startup (idempotent).
- CLI `--memory` uses `MemorySaver` (no DB).

### FR-03 — Classifier agent

- Input: `transcript`
- Output via `Command(goto="structure_agent", update={complexity, reformulated_transcript})`
- Structured model via `complete_structured`

### FR-04 — Structure agent

- Calls `run_structure_agent` on reformulated brief
- Maps `complexity` → reasoning effort via settings map
- Writes `structure` (modules → tasks, no hours)

### FR-05 — Human gate 1 (`structure_review`)

- `interrupt()` with payload for UI review
- Resume decision: `{approved: bool, modules?: [...]}`
- Approved modules drive `Send` fan-out

### FR-06 — Per-task hours fan-out

- One `estimate_task_hours` branch per approved task
- Reuse `estimate_one_task` (adapt signature / DI to graph node)
- Accumulator uses **keyed** `merge_task_hours` (idempotent on resume)

### FR-07 — Recover and handover

- Flag doubtful tasks (no match / contradictory range / low reliability)
- Run `run_task_hours_recovery_agent` when flagged
- `Command(goto="analysis_agent", update={estimate, …})`

### FR-08 — Analysis + human gate 2 (`final_review`)

- Analysis produces `ReliabilityReport` (structured LLM)
- Gate 2 resume: `{validated, estimate_overrides?, want_proposal}`
- Sets `status` (`validated` | `needs_review`)

### FR-09 — Proposal agent (bonus)

- Only when `GRAPH_PROPOSAL_ENABLED` and `want_proposal`
- Also support on-demand `POST …/proposal` over completed run (official parity)

### FR-10 — HTTP contract

| Verb | Path | Behavior |
| --- | --- | --- |
| POST | `/api/v1/estimate/graph` | Start → pause at gate 1 or complete |
| POST | `/api/v1/estimate/graph/{id}/resume` | Resume; 409 if nothing pending |
| GET | `/api/v1/estimate/graph/{id}/state` | Snapshot; 404 unknown |
| POST | `/api/v1/estimate/graph/stream` | 202 + background `astream` (optional slice) |
| GET | `/api/v1/estimate/graph/{id}/progress` | `running` \| `paused` \| `completed` + activity |
| POST | `/api/v1/estimate/graph/{id}/proposal` | Draft commercial proposal |

Auth: `ESTIMATE_API_KEY` (same as RAG estimate). Rate limits aligned with estimate
routes (≈10/min write, higher for progress poll). Graph unavailable → **503**.
Node/LLM failures → **502** (safe message, no secrets).

### FR-11 — CLI deliverable

```bash
# Partial offline: MemorySaver + stub hours (still needs OPENAI_API_KEY for LLM agents)
uv run python app/scripts/run_graph_s13.py --memory --stub

# Full path (Postgres checkpointer + real task-hours retrieval)
uv run python app/scripts/run_graph_s13.py \
  --out exercises/session-13/example_run_complex.txt
```

Auto-approves both gates with canned `Command(resume=…)` decisions.

### FR-12 — Tests (network-free)

- Fast suite: MemorySaver + faked `complete_structured` + faked
  `run_structure_agent` / `estimate_one_task` / recovery
- Assert: pause at both gates, resume works, fan-out row count, keyed reducer no
  duplicates, recovery path when flagged, proposal route when requested
- No real API keys / no Postgres required for default `uv run pytest`

### FR-13 — Additive safety

- Existing `/api/v1/estimate/agent`, RAG, CAG, sessions unchanged
- Graph init failure must not take down other routers

---

## Technical Approach

### File mapping (official → `master-ia`)

| Official (`estimator/app/...`) | Proposed `master-ia` location |
| --- | --- |
| `domain/graph/state.py` | `app/services/estimation_graph/state.py` |
| `domain/graph/build.py` | `app/services/estimation_graph/build.py` |
| `domain/graph/checkpointer.py` | `app/services/estimation_graph/checkpointer.py` |
| `domain/graph/observability.py` | `app/services/estimation_graph/observability.py` |
| `domain/graph/personas.py` | `app/services/estimation_graph/personas.py` |
| `domain/graph/schemas.py` | `app/services/estimation_graph/schemas.py` |
| `domain/graph/activity.py` | `app/services/estimation_graph/activity.py` |
| `domain/graph/agents/*` | `app/services/estimation_graph/agents/*` |
| `domain/graph/nodes.py` | `app/services/estimation_graph/nodes.py` (optional teaching) |
| `domain/schemas/graph_estimation.py` | `app/schemas/graph_estimation.py` |
| `api/routers/estimate_graph.py` | `app/routers/estimate_graph.py` |
| `generation/agentic/agent_loop.py` (two-phase) | extend `app/services/agentic/agent_loop.py` |
| `generation/agentic/agent_schemas.py` / tools | extend `app/services/agentic/*` |
| `generation/rag/task_hours.estimate_one` | wrap `app/services/rag_task_hours.estimate_one_task` |
| `scripts/run_graph_s13.py` | `app/scripts/run_graph_s13.py` |
| `exercises/session-13/` | `exercises/session-13/` |
| `tests/domain/graph/` | `tests/estimation_graph/` |

### Dependency injection pattern

Official nodes call `from app.dependencies import get_llm_wrapper` inside the node.
In `master-ia`, prefer:

- Thin getters in `app/deps.py` (or graph-local `dependencies.py`) for
  `complete_structured` settings, AsyncOpenAI client, embedder, DB session factory
- Graph nodes remain `state → partial update | Command` with monkeypatch-friendly
  **module-level** imports for tests (mirror official test style)

### Lifespan sketch

```python
# app/main.py lifespan (additive)
app.state.graph = None
try:
    async with open_checkpointer() as checkpointer:  # or AsyncExitStack
        app.state.graph = build_graph(checkpointer)
        yield
except Exception:
    # log graph_init_failed; leave graph=None; still serve other routes
    yield
```

Exact `AsyncExitStack` pattern should follow official `main.py` so the pool closes
cleanly.

### Data flow

```text
Client transcript
  → POST /api/v1/estimate/graph (thread_id = estimation_id)
  → classifier → structure → interrupt(structure_review)
  → Client UI / CLI resume
  → Send×N estimate_task_hours → recover_and_handover
  → analysis → interrupt(final_review)
  → Client resume → optional proposal → GraphRunState(completed)
```

### Layering

- Routers orchestrate only; graph package owns orchestration
- Graph may call `rag_task_hours` and `agentic` (same “conductor” role as official
  `domain/`)
- Do **not** import routers from graph services

---

## Acceptance Criteria

- [ ] **AC-01:** `uv add` lands `langgraph`, `langgraph-checkpoint-postgres`, and
      `psycopg` (binary) without breaking the fast pytest suite import path.
- [ ] **AC-02:** `run_structure_agent` + `run_task_hours_recovery_agent` exist with
      unit tests (mocked Responses); no real API key in default suite.
- [x] **AC-03:** `build_graph(MemorySaver())` runs end-to-end in tests: pauses at
      gate 1, resumes, pauses at gate 2, completes with `status` set.
- [x] **AC-04:** Fan-out produces one `task_hours` row per approved task; resume
      re-entry does **not** duplicate rows (`merge_task_hours`).
- [x] **AC-05:** Flagged task path invokes recovery agent (asserted via fake).
- [ ] **AC-06:** `POST /api/v1/estimate/graph` without key returns 401 when
      `ESTIMATE_API_KEY` is set; with key returns `GraphRunState`.
- [ ] **AC-07:** Resume without pending gate returns **409**; unknown id state
      returns **404**; graph not built returns **503**.
- [ ] **AC-08:** CLI `--memory --stub` completes with auto-approved gates (manual /
      `@pytest.mark.slow` optional).
- [ ] **AC-09:** Checkpointer tables coexist with pgvector (`checkpoints*` created
      via `setup()`); documented in README.
- [ ] **AC-10:** Existing agent/RAG/CAG tests still pass; graph init failure does
      not break `/health`.
- [ ] **AC-11:** Settings documented in `.env.example` + README; technical note
      under `docs/technical/`.
- [ ] **AC-12 (optional stream slice):** `POST /graph/stream` returns 202;
      `GET /progress` eventually shows `paused` or `completed` with activity lines.
- [ ] **AC-13 (optional UI):** React screen can drive start → gate 1 → resume →
      gate 2 → complete (may be `front-feature-NNN` child).

---

## Test Plan

### Unit tests

- `tests/services/agentic/test_structure_and_recovery_agents.py` — two-phase APIs
- `tests/estimation_graph/test_state.py` — `merge_task_hours` idempotency
- `tests/estimation_graph/test_build_routing.py` — `fan_out_hours`, `route_after_gate2`
- `tests/estimation_graph/test_graph.py` — full MemorySaver e2e with fakes
- `tests/estimation_graph/test_checkpointer_conninfo.py` — DSN stripping
- `tests/routers/test_estimate_graph.py` — auth, 409/404/503, response shape

### Integration tests

- Optional `@pytest.mark.slow`: real Postgres checkpointer setup against docker
  compose (not required for default suite)

### Manual checks

```bash
uv run pytest tests/estimation_graph tests/services/agentic -q
uv run pytest -q   # full fast suite still green
uv run python app/scripts/run_graph_s13.py --memory --stub
# With stack up + task corpus ingested:
uv run python app/scripts/run_graph_s13.py --out exercises/session-13/example_run_complex.txt
```

---

## Verification

- **Automated:** fast pytest graph + agentic + router tests; full default suite
- **Manual:** CLI `--memory --stub`; optional full Postgres run
- **Not verified yet:** Live Logfire export aesthetics; React wizard UX; byte-identical
  estimates vs official (schema/model drift expected)

---

## Documentation Plan

| Artifact | Update |
| --- | --- |
| `.env.example` | Graph settings |
| `README.md` | Session 13 section: endpoints, CLI, checkpointer note |
| `docs/technical/estimation-graph-s13.md` | Architecture, topology, fork decisions |
| `exercises/session-13/README.md` | Student-facing runbook (English technical voice) |
| `learnings/second-brain-master-ia/...` | Session 13 learning note (Spanish OK for reflection) |
| `feature-053` handoff | Cross-link: S13 track starts at feature-066 (optional one-line) |

---

## Implementation Plan

- [x] **Step 1:** Add deps (`langgraph`, checkpoint-postgres, `psycopg`) + settings
      stubs + `.env.example` entries.  
      *TDD:* `tests/estimation_graph/test_checkpointer_conninfo.py` RED → GREEN for DSN helper.
- [x] **Step 2:** Evolve `app/services/agentic/` with `run_structure_agent` +
      `run_task_hours_recovery_agent` + schemas/tools.  
      *TDD:* mocked Responses tests RED → GREEN.
- [x] **Step 3:** Port `state.py` + `merge_task_hours` + routing helpers in `build.py`
      (graph not fully wired yet).  
      *TDD:* reducer + routing unit tests.
- [x] **Step 4:** Port agents + gates; `build_graph` compiles with MemorySaver.  
      *TDD:* `test_graph.py` e2e RED → GREEN (fakes).
- [ ] **Step 5:** Checkpointer + lifespan wiring (`app.state.graph`).  
      *Verification:* app starts when Postgres down with `graph=None`; `/health` OK.
- [ ] **Step 6:** HTTP router (start / resume / state) + auth/rate-limit + tests.
- [ ] **Step 7:** CLI `run_graph_s13.py` + `exercises/session-13/` assets + README.
- [ ] **Step 8:** Optional stream/progress/proposal endpoints + activity log.
- [ ] **Step 9:** Docs (`docs/technical/…`, README) + Second Brain note.
- [ ] **Step 10 (optional child):** React graph wizard (`/write-front-feature`).

Suggested commit cadence: one step ≈ one commit (≤ ~100–200 meaningful lines where
practical; deps commit separate).

---

## Learnings

1. **Official S12 on `session_13_live` is not the same as `feature-054`.** The live
   repo split the agent into structure + recovery phases; porting only LangGraph
   without that evolution will fail at `structure_agent` / `recover_and_handover`.
2. **Keyed reducers matter.** Plain `operator.add` on `task_hours` duplicates rows
   on resume — official teaches this with `merge_task_hours`.
3. **Checkpointer ≠ SQLAlchemy engine.** `AsyncPostgresSaver` needs psycopg3 + plain
   DSN + pool for long human pauses.
4. **Graph init must be optional infrastructure.** A down Postgres should 503 graph
   routes, not crash the whole API.
5. **Do not port `structlog` or Rails.** Capability parity, not stack clone.
6. **`estimate_one_task` already exists** in `master-ia` — wrap it; do not reimplement
   consensus math.
7. **feature-053 residuals are not S13.** Keep FR-20 / corpus jobs / chunker lab UI
   as separate follow-ups.

---

## Estimation

| Slice | Relative effort | Risk |
| --- | --- | --- |
| Step 1 deps/settings | S | Low |
| Step 2 S12 two-phase evolution | M | Medium (Responses tools) |
| Steps 3–4 graph core | L | Medium (LangGraph APIs) |
| Steps 5–6 HTTP + lifespan | M | Medium (async pool) |
| Step 7 CLI/exercises | S | Low |
| Step 8 stream/progress | M | Low–medium |
| Step 10 React wizard | M | Low (UX) |

**Total:** large multi-commit feature; prefer `/start-task` on this document and
split stream/UI if the core PR grows past reviewability.

---

## Implementation progress

- [x] Step 1: deps (`langgraph`, `langgraph-checkpoint-postgres`, `psycopg[binary]`, `psycopg-pool`) + `GRAPH_*` settings + `.env.example` + `saver_conninfo` (2026-07-19)
- [x] Step 2: two-phase agentic APIs (`run_structure_agent`, `run_task_hours_recovery_agent`, `derive_task_hours`) + mocked tests (2026-07-19)
- [x] Step 3: `EstimationState` + `merge_task_hours` + `fan_out_hours` / `route_after_gate2` (2026-07-19)
- [x] Step 4: agents + `build_graph(MemorySaver)` e2e (2026-07-19)
- [ ] Step 5: checkpointer + lifespan
- [ ] Step 6: HTTP router
- [ ] Step 7: CLI + exercises
- [ ] Step 8: optional stream/progress/proposal
- [ ] Step 9: docs + Second Brain
- [ ] Step 10: optional React wizard (child)

---

## Pull Request

- Draft: https://github.com/povedica/master-ia-lidr/pull/60 (label: `wip`)

---

## How to start

```text
/start-task docs/work-items/feature-066-langgraph-multi-agent-estimation-s13.md
```

If you only want the React wizard after the API lands, run `/write-front-feature`
for a child front work item that consumes `/api/v1/estimate/graph*`.
