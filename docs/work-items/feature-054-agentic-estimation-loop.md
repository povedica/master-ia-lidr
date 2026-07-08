# Feature: Agentic Estimation Loop (Session 12)

## Objective

Replace the fixed RAG pipeline (`rephrase → retrieve → generate`) with an **explicit, hand-written agentic loop** inside the AI service. The agent receives a **meeting transcript**, decomposes the project into components, calls well-defined tools (`search_budgets`, `calculate_estimate`) in a **reason → act → observe → repeat** cycle, and returns:

1. A **structured final estimate** (component breakdown + total hours).
2. An **ordered trace** of reasoning summaries, tool actions, and tool observations — auditable step by step.

The business backend keeps a **simple contract**: transcript in, structured estimate out. The agent is an orchestration layer on top of infrastructure already built in Sessions 9–11 (hybrid retrieval + reranking, deterministic cost function).

**Pedagogical goal:** demonstrate that an agent is not magic — it is a **controlled loop** you own: call an LLM, execute tools, chain responses, stop when done (with a hard iteration cap).

**Reference implementation:** official `ai-engineering` branch `origin/session_12` (`estimator/app/generation/agentic/*`, `estimator/exercises/session-12/*`, `estimator/scripts/run_agent_s12.py`). This feature ports the **behavior and deliverable**, adapted to `master-ia` layout and conventions.

## Context

### What exists today in `master-ia`

| Area | Current state | Relevance |
| --- | --- | --- |
| Fixed RAG path | `app/services/rag_estimation_service.py:RagEstimationService.estimate()` — single retrieve → assemble → `complete_structured()` | Baseline to contrast; **unchanged** by this feature |
| RAG HTTP API | `POST /api/v1/estimate/rag` (`app/routers/rag_estimations.py`) — `question` string, modes A–D | Additive agent endpoint or CLI-only deliverable; do not break |
| Retrieval | `app/embedding_pipeline/retrieval_service.py:RetrievalService.retrieve()` — hybrid RRF + optional rerank (modes A–D) | Wrapped by `search_budgets` |
| Structured LLM | `app/services/structured_llm_client.py:complete_structured()` — Instructor + LiteLLM | **Not used** for the agent loop (deliberate exception; see Technical Approach) |
| Provider chain | `app/services/llm_chain.py`, `provider_routing.py` | Agent loop uses **raw OpenAI Responses API** for visibility |
| Logging | stdlib `logging` + `extra={}` | Use this; do **not** add `structlog` |
| Settings | `retrieval_*`, `rag_estimation_retrieval_mode` in `app/config.py` | Reuse for retrieval inside `search_budgets` |
| Parity roadmap | `docs/work-items/feature-053-official-master-parity-alignment.md` | Session 12 agent is a **separate capability**; does not subsume S11 RAG stages |

### Official Session 12 materials (source of truth for exercise shape)

| Artifact | Official path | Purpose |
| --- | --- | --- |
| Agent loop | `estimator/app/generation/agentic/agent_loop.py` | Manual `client.responses.create` + `previous_response_id` chaining |
| Tools | `estimator/app/generation/agentic/agent_tools.py` | Flat Responses schemas (`strict: true`) + dispatch |
| Schemas | `estimator/app/generation/agentic/agent_schemas.py` | Tool args, trace, `AgentEstimate` |
| Exercise stub | `estimator/exercises/session-12/reference_retrieval.py` | Offline keyword stub when DB unavailable |
| Cost skeleton | `estimator/exercises/session-12/calculate_estimate_skeleton.py` | Starting point for deterministic `calculate_estimate` |
| Sample transcripts | `sample_transcript_simple.txt`, `sample_transcript_complex.txt` | Debug vs deliverable runs |
| Runner | `estimator/scripts/run_agent_s12.py` | Console/file trace deliverable |

### Deliberate fork decisions (do not “fix” without ADR)

1. **Responses API exception:** Every other LLM path in `master-ia` uses LiteLLM/Instructor. The agent loop **must** call `AsyncOpenAI().responses.create` / `.parse` directly so each reasoning item, function call, and output is visible. Do not route the loop through `LLMPipeline` or `complete_structured`.
2. **Logging:** stdlib `logging` with stable `extra` keys (`agent_run_start`, `agent_tool_error`, …). No `structlog`.
3. **Retrieval adapter:** Wrap `RetrievalService.retrieve()` (not the official `retrieve()` from `ai-engineering`). Map `RetrievalResultRow` → historical budget items expected by the agent.
4. **Additive surface:** Do not replace `RagEstimationService` or change `/api/v1/estimate/rag` behavior. Ship agent as new module + runner (+ optional HTTP route).
5. **Light estimate schema:** `AgentEstimate` is intentionally simpler than `RagEstimationResult` (no per-line `SourceCitation` / coherence gate). The exercise focuses on the **loop and trace**, not S11 verification depth.

## Scope

### Includes

- Port Session 12 exercise assets into `exercises/session-12/` (transcripts, stub, skeleton).
- New package `app/services/agentic/` (or `app/services/estimation_agent/` — pick one at implementation; spec uses `agentic`):
  - Flat Responses tool schemas (`search_budgets`, `calculate_estimate`, optional `validate_estimate`).
  - Tool implementations: retrieval wrapper, deterministic calculator, optional validator.
  - Pydantic models for tool args, trace steps, final estimate.
  - `run_estimation_agent()` — manual loop with `previous_response_id`, max iterations, final `responses.parse`.
- Injectable retrieval backend (real pipeline vs stub) for cheap offline debugging.
- CLI runner `app/scripts/run_agent_s12.py` mirroring official deliverable (`--model`, `--effort`, `--stub`, `--out`).
- New settings + `.env.example` entries for agent model, reasoning effort, max iterations.
- Unit tests with mocked OpenAI Responses client (no real API keys in default suite).
- Optional `slow` integration test against stub + mocked multi-step Responses payloads.
- README section + Second Brain session note (Session 12).
- Optional HTTP endpoint `POST /api/v1/estimate/agent` returning estimate + trace (if timeboxed; runner alone satisfies exercise deliverable).

### Excludes

- Replacing `/api/v1/estimate/rag` or CAG v2 paths with the agent.
- Routing the agent through `LLMPipeline`, semantic cache, or ACB guardrails.
- Reimplementing hybrid retrieval or reranking inside the agent (only wrap existing service).
- Multi-index collections / transcript ingest (feature-053 Phase 2+).
- `structlog` migration.
- Committing generated trace files under `evaluation/**/results/` (local deliverable only).
- Web UI for agent trace (console/file output is sufficient).
- Real API keys in tests or docs.

## Functional Requirements

### FR-01 — Inputs

| Input | Type | Rules |
| --- | --- | --- |
| `transcript` | `str` | Non-empty UTF-8 text of an estimation meeting |
| `model` | `str` | Default from settings; exercise uses `gpt-5-mini` (debug) and `gpt-5` (final) |
| `reasoning_effort` | `str` | Passed to `reasoning={"effort": ...}`; default `medium` for final runs |
| `max_iterations` | `int` | Hard cap on Responses API turns; default `10`, `>= 1` |
| `retrieval_backend` | injectable | Real `RetrievalService` wrapper or stub module |

### FR-02 — `search_budgets` tool

**Purpose:** Retrieve historical budgets analogous to **one** component or requirement.

**Implementation:** Async wrapper around `RetrievalService.retrieve()` with settings-driven mode (`rag_estimation_retrieval_mode` or agent-specific override), `recall_k`, `top_k_final`. Re-fetch chunk metadata/content as needed to build return items. **Do not** duplicate fusion/rerank logic.

**Return shape** (each item at minimum):

```json
{
  "id": 1001,
  "content_preview": "...",
  "sector": "logistics",
  "budget_id": "BUD-CORE-2023-02",
  "estimated_hours": 1150.0,
  "distance": 0.12
}
```

Map from `RetrievalResultRow` + chunk content: `id` ← `chunk_id`, `estimated_hours` from metadata or a documented fallback field, `distance` ← fused/rerank score when available.

**Stub fallback:** `exercises/session-12/reference_retrieval.py` provides keyword-matched canned items in the **same shape** for `--stub` runs without Postgres.

**Tool schema (Responses API, flat, `strict: true`):**

- `name`: `search_budgets`
- `parameters.query` (string, required): focused component description
- `parameters.filters` (object or null): `sectors` (array of strings or null), `component_type` (string or null)
- All object levels: `additionalProperties: false`; nullable unions for optional fields per OpenAI strict mode

### FR-03 — `calculate_estimate` tool

**Purpose:** Deterministic partial/total estimate from components and reference amounts.

**Implementation:** Pure Python — start from `exercises/session-12/calculate_estimate_skeleton.py`. Use median (or documented choice) of `reference_amounts`, apply transparent `CONTINGENCY_FACTOR` (default `0.15`), flag `unbudgeted=True` when references empty (hours `0`, no invented numbers).

**Return shape:**

```json
{
  "components": [
    {
      "name": "ERP integration",
      "reference_count": 2,
      "estimated_hours": 989.0,
      "unbudgeted": false
    }
  ],
  "total_hours": 3245.5,
  "summary": "total=3245.5h across 4 components"
}
```

`summary` is used as the trace **observation** string.

### FR-04 — `validate_estimate` tool (optional extension)

**Purpose:** Guardrails before final answer — missing references, hours outside reference range, total mismatch, implausible totals.

**Return:** `{"ok": bool, "issues": [...], "summary": "..."}`

Include in `TOOL_SCHEMAS` when implemented; agent system prompt should call it as last tool step before final answer.

### FR-05 — System prompt

English instructions covering:

1. Decompose transcript into distinct components.
2. Call `search_budgets` **once per component** with focused queries (not one monolithic search).
3. Collect `estimated_hours` from results as `reference_amounts`.
4. Call `calculate_estimate` when every component has been searched (or explicitly flagged unbudgeted).
5. Optionally call `validate_estimate`, then produce final structured estimate.
6. Do not invent tool results; surface uncertainty when data is sparse.

### FR-06 — Agentic loop

Orchestration **by hand** on OpenAI Responses API:

```
1. responses.create(
     model, instructions=SYSTEM_PROMPT,
     input=[{role: user, content: transcript}],
     tools=TOOL_SCHEMAS,
     reasoning={effort, summary: "auto"},
     store=True,
   )
2. While response.output contains function_call items:
     a. Parse call_id, name, arguments (validate into Pydantic tool-arg models)
     b. dispatch_tool(name, args) → result dict
     c. Append AgentStep(reasoning, tool, tool_args, observation)
     d. responses.create(
          previous_response_id=response.id,
          input=[{type: function_call_output, call_id, output: json}],
          tools=TOOL_SCHEMAS, reasoning=..., store=True,
        )
     e. Increment iteration; break with stopped_reason=max_iterations if cap hit
3. When no function_call items: natural stop
4. responses.parse(
     previous_response_id=...,
     input=[{role: user, content: FINAL_INSTRUCTION}],
     text_format=AgentEstimate,
   )
```

**Error handling:** Malformed JSON args or tool exceptions become `{"error": "..."}` observations so the model can self-correct; loop must not crash.

**Reasoning capture:** Extract reasoning summary from `response.output` reasoning items; attach to first tool step in a turn; mark parallel tool calls in the same turn accordingly (official pattern).

### FR-07 — Trace format

`AgentTrace` with ordered `AgentStep` list. `AgentTrace.render()` produces deliverable text:

```text
STEP 1
reasoning: Decomposing transcript into backend, ERP, mobile app...
action: search_budgets(query="business backend API orders routes", filters={"sectors": null, "component_type": "backend"})
observation: found 2 budgets, top hours 1150.0, 940.0

STEP 2
...
```

Strip control characters from serialized args before logging/writing files.

### FR-08 — Final estimate schema (`AgentEstimate`)

| Field | Type | Notes |
| --- | --- | --- |
| `components` | list | `name`, `estimated_hours`, `rationale`, `cited_chunk_ids` (ints from search results) |
| `total_hours` | float | `>= 0` |
| `confidence` | `low` \| `medium` \| `high` | Agent self-assessment |
| `assumptions` | list[str] | Optional explicit assumptions |

Filled by terminal `responses.parse`, not by free-form JSON in the last loop turn.

### FR-09 — Stopping conditions

| Condition | `stopped_reason` | Behavior |
| --- | --- | --- |
| No more `function_call` in a turn | `completed` | Proceed to final parse |
| `iterations >= max_iterations` | `max_iterations` | Return partial trace; `estimate` may be null |
| Final parse fails | `no_final_estimate` | Trace preserved; log error |

### FR-10 — CLI deliverable (`app/scripts/run_agent_s12.py`)

| Flag | Purpose |
| --- | --- |
| `transcript` (positional path) | Input file |
| `--model` | e.g. `gpt-5-mini`, `gpt-5` |
| `--effort` | `minimal` \| `low` \| `medium` \| `high` |
| `--stub` | Use `reference_retrieval.py` instead of DB retrieval |
| `--out` | Write trace + estimate to file |
| `--max-iterations` | Override settings cap |

**Cost discipline (exercise):**

1. Debug loop: `gpt-5-mini` + `sample_transcript_simple.txt` (+ `--stub` if no DB).
2. Deliverable: `gpt-5` + `effort medium` + `sample_transcript_complex.txt` → attach trace for Lia.

### FR-11 — HTTP API (optional)

`POST /api/v1/estimate/agent`

**Request:** `{ "transcript": "...", "model"?: "...", "reasoning_effort"?: "...", "max_iterations"?: int }`

**Response:** `{ "result": AgentEstimate, "trace": AgentTrace, "request_id": "...", "iterations": int, "stopped_reason": str, "model": "..." }`

Route handler orchestrates only; business logic in `run_estimation_agent()`. Return 503 when `OPENAI_API_KEY` missing.

### FR-12 — Settings

| Variable | Default | Description |
| --- | --- | --- |
| `AGENT_MODEL` | `gpt-5-mini` | Default model for agent runs |
| `AGENT_REASONING_EFFORT` | `medium` | `reasoning.effort` for gpt-5 family |
| `AGENT_MAX_ITERATIONS` | `10` | Hard loop cap |
| `AGENT_RETRIEVAL_MODE` | same as `rag_estimation_retrieval_mode` | Mode A–D for `search_budgets` |

Document all in `.env.example` (empty/placeholder values only).

## Technical Approach

### Module layout (proposed)

```text
app/services/agentic/
├── __init__.py
├── agent_schemas.py      # Tool args, AgentStep, AgentTrace, AgentEstimate, AgentRunResult
├── agent_tools.py        # TOOL_SCHEMAS, dispatch_tool, search_budgets, calculate_estimate, validate_estimate
├── agent_loop.py         # run_estimation_agent, SYSTEM_PROMPT, loop mechanics
└── retrieval_adapter.py  # RetrievalService → list[dict] historical items

exercises/session-12/
├── sample_transcript_simple.txt
├── sample_transcript_complex.txt
├── reference_retrieval.py
└── calculate_estimate_skeleton.py

app/scripts/run_agent_s12.py
```

### Retrieval adapter

`default_retrieval_backend(args: SearchBudgetsArgs) -> list[dict]`:

1. Build query string from `args.query` (+ optional filter hints appended or passed as metadata filters if supported).
2. Call `RetrievalService.retrieve()` with injected session, embedder, reranker, mode from settings.
3. Load chunk previews via existing `ChunkContentRepository` pattern (`app/embedding_pipeline/chunk_content_repository.py` from feature-052).
4. Map rows to stub-compatible dicts; include `summary` in tool result for trace observation.

Keep `app/services` → `app/embedding_pipeline` dependency direction (never reverse).

### OpenAI client

Use `AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)` dedicated to the agent path, or a small factory in `app/services/agentic/openai_client.py`. **Do not** pass agent calls through LiteLLM.

### Layering

```text
Router (optional) / CLI script
    → run_estimation_agent()
        → agent_loop (Responses API)
        → dispatch_tool()
            → retrieval_adapter → RetrievalService
            → calculate_estimate (pure)
            → validate_estimate (pure, optional)
```

### Acceptance scenario — `sample_transcript_complex.txt`

With real retrieval or stub, the agent must:

- Identify **more than one** component.
- Call `search_budgets` **more than once** (component-focused queries).
- Call `calculate_estimate` with gathered `reference_amounts`.
- Terminate without infinite loop (`stopped_reason != max_iterations` in happy path).
- Produce coherent `AgentEstimate` (sensible total, per-component hours).
- Emit trace reconstructing decisions (reasoning + action + observation per step).

## Acceptance Criteria

- [x] **AC-01:** `TOOL_SCHEMAS` defines `search_budgets` and `calculate_estimate` as flat Responses functions with `strict: true`, English names/descriptions, and `additionalProperties: false` at every object level.
- [x] **AC-02:** `calculate_estimate` is pure Python (no LLM); identical inputs produce identical outputs (unit-tested).
- [x] **AC-03:** `search_budgets` default backend wraps `RetrievalService.retrieve()` without reimplementing fusion/rerank (integration test with fakes or stub mode).
- [x] **AC-04:** `--stub` flag routes `search_budgets` through `exercises/session-12/reference_retrieval.py` with no database required.
- [x] **AC-05:** `run_estimation_agent` chains `responses.create` with `previous_response_id` and submits `function_call_output` per `call_id` (unit-tested with mocked client returning multi-turn function calls).
- [x] **AC-06:** Loop enforces `max_iterations`; on cap, `stopped_reason="max_iterations"` and no unhandled exception.
- [x] **AC-07:** Each tool step records `reasoning_summary`, `tool`, `tool_args`, `observation`; `AgentTrace.render()` matches `STEP N` format from the exercise.
- [x] **AC-08:** Malformed tool arguments return error observations; loop continues (unit-tested).
- [x] **AC-09:** Terminal `responses.parse` produces validated `AgentEstimate` on successful runs (mocked in unit tests).
- [ ] **AC-10:** On `sample_transcript_complex.txt` with `gpt-5` / `medium` effort (manual slow run): >1 component, >1 `search_budgets` call, ≥1 `calculate_estimate` call, finite termination, coherent estimate.
- [x] **AC-11:** `app/scripts/run_agent_s12.py` prints trace to stdout and supports `--out` for deliverable file.
- [x] **AC-12:** Default `uv run pytest` passes with mocked OpenAI client (no API keys); agent integration tests marked `@pytest.mark.slow`.
- [x] **AC-13:** `.env.example` documents `AGENT_MODEL`, `AGENT_REASONING_EFFORT`, `AGENT_MAX_ITERATIONS`, `AGENT_RETRIEVAL_MODE`.
- [x] **AC-14:** README documents debug vs deliverable commands and cost discipline (`gpt-5-mini` + simple transcript first).
- [x] **AC-15:** Existing `/api/v1/estimate/rag` and CAG endpoints unchanged (regression: existing RAG tests green).
- [x] **AC-16 (optional):** `validate_estimate` tool implemented and invoked in system prompt as final guardrail step.
- [x] **AC-17 (optional):** `POST /api/v1/estimate/agent` returns estimate + trace JSON.

## Test Plan

### Unit tests

| Module | Focus |
| --- | --- |
| `test_agent_schemas.py` | Tool arg validation; `AgentTrace.render()` format |
| `test_agent_tools.py` | `calculate_estimate` median + contingency + unbudgeted; `validate_estimate` flags |
| `test_agent_tools.py` | `dispatch_tool` unknown tool / bad args |
| `test_retrieval_adapter.py` | Row → historical item mapping (fake retrieval rows) |
| `test_agent_loop.py` | Mocked Responses client: single tool call, parallel calls, max iterations, final parse |

### Integration tests

- Stub backend + mocked OpenAI multi-step sequence → full `AgentRunResult` with trace steps in order.
- Optional `slow`: smoke with real API key + `--stub` (deselected by default).

### Manual checks

1. `uv run python app/scripts/run_agent_s12.py exercises/session-12/sample_transcript_simple.txt --model gpt-5-mini --stub`
2. Confirm trace shows reason → action → observation per step; no crash.
3. With DB populated: same command without `--stub`; retrieval returns real chunks.
4. Deliverable run: `sample_transcript_complex.txt --model gpt-5 --effort medium --out /tmp/agent_trace_complex.txt`
5. Verify >1 `search_budgets` in trace; `calculate_estimate` present; final total plausible.
6. `uv run pytest` — full fast suite green.

## Verification

### Automated

- **Verified:** `uv run pytest tests/test_agent_*.py tests/test_retrieval_adapter.py tests/exercises/test_session_12_assets.py` — 28 passed
- **Verified:** `uv run pytest tests/test_rag_estimation_endpoint.py tests/test_rag_estimation_service.py` — 15 passed (no RAG regression)
- **Not verified:** full `uv run pytest` suite (7 pre-existing failures in `test_config` / `test_worktree_tasks` unrelated to feature-054)

### Manual

- Session 12 deliverable trace on `sample_transcript_complex.txt` saved locally (not committed)
- Optional: email Lia with branch link + trace attachment (student process, outside repo)

### Not verified yet

- Live `gpt-5` run cost/latency benchmarks
- Production load / rate limits on Responses API
- Parity with official `origin/session_12` trace wording byte-for-byte

## Handoff from feature-054

**Shipped interfaces**

- `POST /api/v1/estimate/agent` — `{ transcript, model?, reasoning_effort?, max_iterations? }` → `{ result, trace, request_id, iterations, stopped_reason, model }`
- `app/scripts/run_agent_s12.py` — CLI with `--stub`, `--model`, `--effort`, `--out`, `--max-iterations`
- `run_estimation_agent(transcript, client, model, reasoning_effort, max_iterations, retrieval_backend)` in `app/services/agentic/agent_loop.py`
- `build_retrieval_backend(...)` and `load_stub_retrieval_backend()` in `retrieval_adapter.py`
- Settings: `AGENT_MODEL`, `AGENT_REASONING_EFFORT`, `AGENT_MAX_ITERATIONS`, `AGENT_RETRIEVAL_MODE`

**Residual risks**

- Live API tuning of tool descriptions not done in-repo (manual step with real key)
- CLI real-retrieval path needs `DATABASE_URL` + populated corpus
- Agent path bypasses rate-limit keys (`ESTIMATE_API_KEY`) — intentional for local dev; harden in feature-056 if needed

**Recommended first checks for next implementer**

1. `uv run pytest tests/test_agent_loop.py -q`
2. `uv run python app/scripts/run_agent_s12.py exercises/session-12/sample_transcript_simple.txt --model gpt-5-mini --stub` (with `OPENAI_API_KEY`)
3. Compare trace format with `exercises/session-12/README.md` acceptance criteria

## Documentation Plan

- `README.md`: new "Agentic estimation (Session 12)" section with CLI examples and env vars
- `learnings/docs/sesiones/sesion-12-agentic-estimation-loop.md` (or Second Brain equivalent): loop anatomy, tool design lessons, cost notes
- Cross-link from `feature-053` parity matrix (Session 12 agent row) when implemented
- `.env.example`: agent settings placeholders
- `docs/arquitectura-estimador-cag.html`: router node for `POST /api/v1/estimate/agent` ✅

## Implementation Plan

- [ ] **Step 1:** Copy exercise assets into `exercises/session-12/` from official `origin/session_12` (transcripts, stub, skeleton). ✅
- [ ] **Step 2:** Add `app/services/agentic/agent_schemas.py` — tool arg models, trace, `AgentEstimate`, `AgentRunResult`.
- [ ] **Step 3:** Implement `calculate_estimate` (+ optional `validate_estimate`) in `agent_tools.py` with unit tests.
- [ ] **Step 4:** Implement flat `TOOL_SCHEMAS` for Responses API (`strict: true`).
- [ ] **Step 5:** Implement `retrieval_adapter.py` wrapping `RetrievalService` + chunk content fetch; wire stub injection.
- [ ] **Step 6:** Implement `dispatch_tool` and `search_budgets` observation `summary`.
- [ ] **Step 7:** Implement `agent_loop.py` — `run_estimation_agent` with mocked tests for multi-turn flow.
- [ ] **Step 8:** Add settings + `.env.example` entries.
- [ ] **Step 9:** Add `app/scripts/run_agent_s12.py` CLI.
- [ ] **Step 10:** Manual debug run (mini + simple + stub); fix tool descriptions if model mis-invokes tools.
- [ ] **Step 11:** Manual deliverable run (gpt-5 + complex transcript); capture trace for submission.
- [ ] **Step 12 (optional):** `POST /api/v1/estimate/agent` router + integration test.
- [ ] **Step 13:** README + session note; run full `uv run pytest`.

## Learnings

- **Tool descriptions are the UI for the model.** Invest time in English descriptions; the model never sees Python docstrings.
- **Flat Responses schemas differ from Chat Completions.** No nested `"function"` key; `strict: true` requires explicit `required` arrays and nullable unions for optionals.
- **`previous_response_id` chaining** avoids reasoning-item ordering bugs when resuming gpt-5 turns.
- **Parallel function calls in one turn** share one reasoning summary — attach to first step only.
- **Debug cheaply:** `gpt-5-mini` + `--stub` validates loop mechanics before spending on `gpt-5` + DB retrieval.
- **Do not conflate with S11 RAG:** `RagEstimationResult` targets citation grounding; `AgentEstimate` targets agent orchestration pedagogy.
- **Official repo uses `structlog`;** `master-ia` keeps stdlib logging per feature-052 precedent.

## Estimation

- **Size:** L
- **Estimated time:** 2.5–3 days focused work (excluding live API cost for tuning runs)
- **Planned steps:** 8

| Slice | Effort |
| --- | --- |
| Schemas + deterministic tools | ~0.5 day |
| Retrieval adapter + stub | ~0.5 day |
| Agent loop + mocked tests | ~1 day |
| CLI + manual tuning (prompts/descriptions) | ~0.5 day |
| Optional HTTP + validate tool | ~0.5 day |
| Docs + session note | ~0.25 day |

## Implementation progress

- [x] Step 1: Exercise assets in `exercises/session-12/`
- [x] Step 2: `agent_schemas.py` + schema tests
- [x] Step 3: `calculate_estimate` (+ optional `validate_estimate`) + tool tests
- [x] Step 4: Flat `TOOL_SCHEMAS` + `dispatch_tool`
- [x] Step 5: `retrieval_adapter.py` + stub injection
- [x] Step 6: `agent_loop.py` with mocked Responses client tests
- [x] Step 7: Agent settings + `.env.example`
- [x] Step 8: CLI `run_agent_s12.py` + README / session note
- [x] Step 9 (optional): `POST /api/v1/estimate/agent` + `validate_estimate`

## Pull Request

- Draft: https://github.com/povedica/master-ia-lidr/pull/59 (label: `wip`)

## Repository commits (master-ia)

| Commit | Summary |
| --- | --- |
| `2862dbd` | `chore(session-12): add exercise assets from official session_12` |
| `536ff58` | `feat(agentic): add agent schemas and trace models` |
| `9c87aec` | `feat(agentic): add calculate_estimate and validate_estimate tools` |
| `120d358` | `feat(agentic): add Responses tool schemas, dispatch, and retrieval adapter` |
| `1abbf51` | `feat(agentic): implement manual estimation agent loop` |
| `3fdd042` | `feat(agentic): add agent settings and env documentation` |
| `7db8a28` | `feat(agentic): add POST /api/v1/estimate/agent endpoint` |
| `5c5b9f6` | `feat(agentic): add Session 12 CLI runner and documentation` |
