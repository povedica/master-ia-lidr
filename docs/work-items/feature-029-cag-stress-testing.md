# Feature: CAG Stress Testing — Instrumentation, Scenarios, Metrics, Runner, and Report

## Objective

Instrument the **current** session-based CAG baseline, stress it with controlled multi-turn and large-attachment scenarios, measure degradation with **deterministic** metrics, and produce quantitative evidence as:

- `evals/stress/results.csv` — one row per conversational turn
- `evals/stress/REPORT.md` — summary tables, three curve sections, and two interpretation paragraphs

This is a **measurement exercise**, not an optimization or RAG migration. Both goals are equally important:

1. **Deliverable**: working stress runner and evidence-based report.
2. **Learning**: understand where CAG degrades silently (cost, latency, memory recall) before accepting RAG in session 6.

## Context

### Production surface (authoritative)

| Concern | Location |
| --- | --- |
| Session create | `POST /api/v1/sessions` → `app/routers/sessions.py::create_session` |
| Session estimate | `POST /api/v1/sessions/{session_id}/estimate` → `estimate_in_session` |
| Orchestration | `SimplifiedSessionEstimationService.run_submit()` in `app/services/simplified_session_estimation_service.py` |
| Guarded LLM path | `LLMPipeline.run_structured()` / `run_structured_with_acb()` in `app/guardrails/llm_pipeline.py` |
| Session state | `Session`, `ConversationHistory`, `ProjectMetadata`, `DerivedProjectMetadata` in `app/services/sessions.py` |
| Session debug (partial) | `GET /api/v1/sessions/{session_id}` → `SessionDetailResponse` in `app/schemas/simplified_session.py` |
| Attachment extraction | `process_attachment_refs()` → `DynamicContextManager.build_context_block()` |
| Usage / cost | `StructuredEstimateBundle.usage` (`UsageInfo`), `estimate_cost_usd()` in `app/services/estimate_response_builder.py` |
| Response assembly | `assemble_estimation_v2_response()` in `app/services/estimation_v2_response_builder.py` |
| Semantic cache signal | `StructuredPipelineOutcome.cached`, `cache_score`, `cache_bucket` from `LLMPipeline` |
| Existing eval harness | `tests/evals/session_runner.py`, `tests/evals/eval_app_factory.py` (httpx + ASGITransport) |

**Important:** The exercise text references `EstimationService.estimate_conversational()`. That path exists in `app/services/conversational_estimation_service.py` but is **not wired to HTTP**. All stress work must target the **simplified session path** above.

### Existing eval pyramid (reuse patterns, separate deliverable)

| Artifact | Location | Reuse for stress |
| --- | --- | --- |
| Golden session replay | `tests/evals/session_runner.py` | HTTP client pattern, session create + multi-turn POST |
| In-process ASGI client | `tests/evals/eval_app_factory.py` | Optional `--in-process` runner mode |
| Hard deterministic assertions | `tests/evals/assertions.py` | Style reference only |
| Judge metrics (out of scope) | `tests/evals/judge/metrics.py` | Do **not** use for MemoryDrift |

There is **no** top-level `evals/metrics.py` or `evals/run.py` today. The exercise deliverable lives under a **new** package `evals/stress/` at repository root (alongside `app/`, `tests/`).

### Code map for `turn_observed` fields (STEP 1)

| Field | Available today | Source / derivation |
| --- | --- | --- |
| `turn_index` | Yes | `session.submit_count` after increment (1-based) |
| `session_id` | Yes | Route param / `Session.session_id` |
| `enriched_transcript_chars` | Derive | `len(user_prompt)` from `_compose_user_prompt()` or transcript + attachment block chars |
| `attachments_total_chars` | Derive | Sum `len(item.text)` from `ExtractedAttachment` in `run_submit` |
| `messages_in_window` | Derive | Count non-system messages in `session.conversation_history.to_messages_list()` after turn |
| `anchors_count` | **Not implemented** | Exercise assumes heuristic anchors; current codebase has none → emit `0` with stable key |
| `summary_chars` | Derive | `len(session.project_metadata.agreed_scope or "")` or `len(merged.summary or "")` |
| `tokens_in` | Partial | `bundle.usage.prompt_tokens` when usage present |
| `tokens_out` | Partial | `bundle.usage.completion_tokens` when usage present |
| `cost_usd` | Partial | `estimate_cost_usd(bundle.model, UsageView(...))` when usage present |
| `latency_ms` | Yes | Router wall-clock in `estimate_in_session` (`perf_counter`) |
| `cache_hit_kind` | Partial | `outcome.pipeline.cached` → `"semantic"`; else `"none"`. No exact-match cache on session path today |
| `last_resolved_tier` | **Not implemented** | No dynamic tiering in session path → emit `"default"` or `null` (pick one, document, stay stable) |

### Gaps vs exercise narrative (document, do not “invent” missing subsystems)

| Exercise concept | Repo reality | Stress approach |
| --- | --- | --- |
| Anchors + cumulative summarizer | Sliding window + compact history + `ProjectMetadata` / `DerivedProjectMetadata` only | MemoryDrift checks `summary` (agreed_scope / derived summary), `metadata` (project_name, constraints, technologies), `anchors` → use `explicit_constraints` as anchor proxy; `anchors_count=0` until a real anchor layer exists |
| `MAX_CONVERSATION_TURNS=6` | `ConversationHistory.max_turns` defaults to **10** | Do **not** change constant during stress; report actual window size |
| `GET /sessions/{id}` debug fields | Returns payload + metadata + `submit_count` only | Extend response with `last_turn_observation` (preferred) rather than parsing logs |
| `evals/metrics.py` + `MetricResult` | Lives under `tests/evals/` with different patterns | Create `evals/stress/metrics.py` with local `MetricResult` dataclass matching exercise contract |
| Exact + semantic cache hit rates | Session path exposes semantic cache via `cached` flag | `cache_hit_kind`: `"semantic"` \| `"none"`; exact rate stays `0` unless exact cache is wired to session pipeline later |
| `dev_mode` usage in API | Token/cost fields only in `EstimationResponse` when `DEV_MODE=true` | Runner sets `DEV_MODE=true` for HTTP runs **or** reads observation from session debug store populated server-side regardless of client-visible fields |

### Logging convention

Production code uses `logging.getLogger(__name__)` with `extra={...}` (see `app/guardrails/llm_pipeline.py`, `app/services/estimation_stats_logger.py`). Emit `turn_observed` the same way:

```python
logger.info("turn_observed", extra={...})
```

No structlog dependency today.

## Scope

### Includes

1. Unified per-turn `turn_observed` log event (13 fields, stable names).
2. Retrievable last-turn observation for the stress runner (session debug extension).
3. `evals/stress/scenarios.py` — deterministic `growing`, `pivot`, `contradiction` families for N ∈ {1, 3, 6, 10, 20}.
4. `evals/stress/fixtures/build_pdfs.py` — reproducible PDFs at ~5, 20, 50, 100 KB.
5. `evals/stress/metrics.py` — `LatencyBudgetMetric`, `CostBudgetMetric`, `MemoryDriftMetric`.
6. `tests/test_stress_metrics.py` — unit tests for the three metrics (no network).
7. `evals/stress/run.py` — CLI runner producing `evals/stress/results.csv`.
8. `evals/stress/REPORT.md` — generated from CSV (tables only, no matplotlib).
9. Minimal README pointer to stress commands and deliverable paths.

### Excludes

- RAG, vector DB, or retrieval pipelines.
- Provider comparison (single provider/model per run).
- CAG optimization (prompt compression, changing `max_turns`, etc.).
- LLM-as-judge for drift or recall.
- Postgres/SQLite persistence for results.
- UI/dashboard for visualization.
- Committing generated PDF binaries (generator script only).
- Notebook / matplotlib dependencies.
- Refactoring `tests/evals/` into `evals/` root (stress is additive).

## Functional Requirements

### FR-01: `turn_observed` event

After each successful `POST /api/v1/sessions/{session_id}/estimate`, emit exactly one `logger.info("turn_observed", extra={...})` containing all 13 fields listed in Context.

- Emit as close as possible to the HTTP return path (router after `run_submit` succeeds and bundle is present).
- Use 1-based `turn_index`.
- Missing conceptual fields use documented defaults (`anchors_count=0`, `last_resolved_tier="default"`).
- Existing API behavior unchanged aside from additive logging and debug exposure (FR-02).

### FR-02: Retrievable observation

Store the latest observation on `Session` (e.g. `last_turn_observation: dict[str, Any] | None`) and expose it via `GET /api/v1/sessions/{session_id}`.

- Add optional field `last_turn_observation` to `SessionDetailResponse`.
- Runner reads observation after each turn without parsing application logs.
- Snapshot for MemoryDrift includes: `project_metadata`, `last_derived_metadata`, `conversation_history` snippet, and `last_turn_observation`.

### FR-03: Synthetic multi-turn scenarios

`evals/stress/scenarios.py` defines:

```python
@dataclass(frozen=True)
class TurnSpec:
    turn_index: int
    transcript: str
    fact_to_remember: str

@dataclass(frozen=True)
class StressScenario:
    scenario_name: str  # growing | pivot | contradiction
    turns: list[TurnSpec]
```

- Factory functions `build_scenario(name: str, n_turns: int) -> StressScenario` for N ∈ {1, 3, 6, 10, 20}.
- Transcripts meet `SessionEstimateRequest` minimum length (80 chars).
- First turn includes required session fields (`project_name`, `project_type`, `target_audience`); later turns may omit them when session already has metadata.
- Facts are short, exact-match friendly (e.g. `"project name: Nimbus"`, `"budget locked: 30000 EUR"`).

### FR-04: Synthetic attachment fixtures

`evals/stress/fixtures/build_pdfs.py` writes:

- `evals/stress/fixtures/attach_5kb.pdf`
- `evals/stress/fixtures/attach_20kb.pdf`
- `evals/stress/fixtures/attach_50kb.pdf`
- `evals/stress/fixtures/attach_100kb.pdf`

- Deterministic repeated text including at least one embeddable fact string.
- Sizes within ±15% of target KB (document actual sizes in REPORT).
- `0 KB` = no attachment (no file).
- Add lightweight PDF writer dev dependency if needed (`fpdf2` recommended; `pypdf` is read-only).

### FR-05: Deterministic stress metrics

`evals/stress/metrics.py`:

```python
@dataclass(frozen=True)
class MetricResult:
    name: str
    score: float
    passed: bool
    details: dict[str, Any]
```

| Metric | Rule |
| --- | --- |
| `LatencyBudgetMetric(budget_ms)` | `score=1.0` if `latency_ms <= budget_ms` else `0.0` |
| `CostBudgetMetric(budget_usd)` | `score=1.0` if `cost_usd <= budget_usd` else `0.0` |
| `MemoryDriftMetric(fact, where=[...])` | `score=1.0` if `fact` appears (case-insensitive substring) in any allowed snapshot location |

Default MemoryDrift locations:

- `summary` → `project_metadata.agreed_scope`, `last_derived_metadata.summary`
- `anchors` → `project_metadata.explicit_constraints`, `last_derived_metadata.detected_constraints`
- `metadata` → serialized `project_name`, `mentioned_technologies`, `detected_constraints`

Evaluate drift only when evaluating turn `k` against a **later** snapshot (runner responsibility).

### FR-06: Stress runner CLI

```bash
uv run python -m evals.stress.run \
  --http http://localhost:8000 \
  --scenarios growing,pivot,contradiction \
  --attachment-sizes 0,5,20,50,100 \
  --repeats 3 \
  --output evals/stress/results.csv
```

Supported flags (minimum):

| Flag | Purpose |
| --- | --- |
| `--http URL` | Run against live uvicorn app |
| `--in-process` | ASGITransport mode (no separate server) |
| `--scenarios` | Comma-separated scenario names |
| `--attachment-sizes` | Comma-separated KB buckets |
| `--repeats` | Repeat index per scenario × attachment |
| `--output` | CSV path |
| `--latency-budget-ms` | Default e.g. `4000` |
| `--cost-budget-usd` | Default e.g. `0.05` |
| `--turn-counts` | Optional override; default all N ∈ {1,3,6,10,20} or fixed N per exercise config |

Core loop:

1. Create session (`POST /api/v1/sessions`).
2. For each turn: `POST .../estimate` (multipart when attachment > 0).
3. `GET .../sessions/{id}` → read `last_turn_observation` + metadata for drift.
4. Evaluate three metrics; append CSV row.

CSV columns (minimum): `scenario_name`, `repeat_index`, `attachment_size_kb`, `turn_index`, `session_id`, all `turn_observed` fields, `metric_latency_budget_score`, `metric_cost_budget_score`, `metric_memory_drift_score`, `fact_to_remember`, `drift_evaluated_against_turn`.

Normal configuration must produce **≥ 50 rows**.

### FR-07: REPORT.md generation

Either generated by `evals/stress/run.py --write-report` or `evals/stress/report.py` invoked after CSV exists.

Contents:

1. **Summary table** — per scenario × attachment size: P50/P95 `latency_ms`, total `cost_usd`, exact cache hit rate, semantic cache hit rate, mean memory drift score.
2. **Curve 1** — table: `latency_ms` vs `tokens_in`.
3. **Curve 2** — table: cumulative `cost_usd` vs `turn_index` (by scenario).
4. **Curve 3** — table: mean `MemoryDriftMetric` vs N (turn count).
5. **Two interpretation paragraphs** — quantitative statements about break point, dominant degradation dimension, and RAG boundary hypothesis.

No plotting libraries.

## Technical Approach

### Step 1 — Inspect and map (read-only)

Produce file/function map (embedded in this document § Context). No code changes.

**Acceptance:** Implementer knows where to add observation, metrics, runner, fixtures, and report.

### Step 2 — `turn_observed` instrumentation

**Files:**

- `app/routers/sessions.py` — aggregate and log after successful estimate.
- Optional helper: `app/services/turn_observation.py` — pure builder for observation dict (keeps router thin).

**Plan:**

1. Add `build_turn_observation(...)` taking session, submit outcome, user_prompt length, attachment chars, latency_ms, cache flags.
2. Call `logger.info("turn_observed", extra=observation)` immediately before `return SessionEstimateResponse(...)`.

### Step 3 — Retrievable observation

**Files:**

- `app/services/sessions.py` — `Session.last_turn_observation: dict[str, Any] | None = None`
- `app/schemas/simplified_session.py` — extend `SessionDetailResponse`
- `app/routers/sessions.py` — persist observation on session after each turn

**Justification:** Deterministic runner consumption beats log parsing; aligns with exercise “preferred option”.

### Step 4 — Scenarios

**Files:**

- `evals/__init__.py`
- `evals/stress/__init__.py`
- `evals/stress/scenarios.py`

Deterministic string templates; no LLM generation.

### Step 5 — PDF fixtures

**Files:**

- `evals/stress/fixtures/build_pdfs.py`
- `evals/stress/fixtures/.gitkeep` or README note

**Dependency:** `uv add --dev fpdf2` (if chosen).

### Step 6 — Metrics

**Files:**

- `evals/stress/metrics.py`

Keep separate from `tests/evals/` because input shape is `turn_observation` + session snapshot, not `EstimationResult`.

### Step 7 — Metric unit tests

**Files:**

- `tests/test_stress_metrics.py`

Import from `evals.stress.metrics`; pure dict fixtures.

### Step 8 — Runner

**Files:**

- `evals/stress/run.py`

Reuse httpx patterns from `tests/evals/session_runner.py`. Map attachment KB → fixture path. Use multipart for file upload (same convention as `tests/test_sessions_integration.py` if present).

**Settings for real LLM runs:**

- `DEV_MODE=true` so usage appears in estimate payload (redundant if FR-02 stores server-side).
- Document required API keys in runner stderr when `--http` fails auth.

### Step 9 — Report

**Files:**

- `evals/stress/report.py` (optional module)
- `evals/stress/REPORT.md` (generated artifact)

Use stdlib `csv` + simple percentile helper (no numpy). Commit **template** `REPORT.md` with placeholder sections only if repo convention requires; otherwise generate entirely from data (exercise expects real numbers after a run).

### Step 10 — Final verification

Checklist in § Verification; update README stress section.

## Acceptance Criteria

- [ ] AC-01: Every successful `POST /api/v1/sessions/{id}/estimate` emits one `turn_observed` log with all 13 fields.
- [ ] AC-02: `GET /api/v1/sessions/{id}` returns `last_turn_observation` matching the latest turn.
- [ ] AC-03: `evals/stress/scenarios.py` exposes `growing`, `pivot`, `contradiction` for N ∈ {1, 3, 6, 10, 20}.
- [ ] AC-04: `build_pdfs.py` regenerates four PDF fixtures deterministically.
- [ ] AC-05: `LatencyBudgetMetric`, `CostBudgetMetric`, `MemoryDriftMetric` return `MetricResult` with deterministic scores.
- [ ] AC-06: `tests/test_stress_metrics.py` passes with `uv run pytest tests/test_stress_metrics.py` (no API keys).
- [ ] AC-07: `uv run python -m evals.stress.run --http http://localhost:8000 ...` completes and writes `evals/stress/results.csv` with ≥ 50 rows.
- [ ] AC-08: CSV contains one row per turn with observation fields and three metric columns.
- [ ] AC-09: `evals/stress/REPORT.md` contains summary table, three curve tables, and two quantitative interpretation paragraphs.
- [ ] AC-10: No RAG, provider comparison, UI, or persistence DB introduced.
- [ ] AC-11: Baseline CAG behavior unchanged except additive observation/debug fields.
- [ ] AC-12: README documents how to run stress test and where deliverables live.

## Test Plan

### Unit tests

- `tests/test_stress_metrics.py`:
  - LatencyBudgetMetric: pass at budget, fail above budget.
  - CostBudgetMetric: pass at budget, fail above budget.
  - MemoryDriftMetric: pass when fact in summary; fail when absent.
  - MemoryDriftMetric: case-insensitive match; missing fields edge case.

### Integration tests (optional, marked `@pytest.mark.slow`)

- Runner in `--in-process` mode with `EvalStructuredLLM` fake: smoke test that CSV rows are written (no real LLM). Defer if timeboxed; manual check acceptable for v1.

### Manual checks

1. Start API: `uv run uvicorn app.main:app --reload` with valid `OPENAI_API_KEY`.
2. Run stress CLI with small subset (`--scenarios growing --attachment-sizes 0 --repeats 1 --turn-counts 3`).
3. Confirm `turn_observed` in logs and `last_turn_observation` in GET response.
4. Full run → open `results.csv` and `REPORT.md`; verify quantitative sentences in interpretation.

## Verification

### Automated

- `uv run pytest tests/test_stress_metrics.py`
- `uv run pytest` (regression; must stay green without API keys for default suite)

### Manual

- End-to-end stress run against local uvicorn with real LLM
- Inspect CSV row count ≥ 50 for default CLI configuration
- Confirm REPORT tables reference actual CSV aggregates

### Not verified yet

- Cross-machine reproducibility of PDF byte sizes
- Semantic cache hit rates when cache disabled in settings
- ACB-on vs ACB-off stress comparison (out of scope; use default settings and document)

## Documentation Plan

- [x] `README.md`: “CAG stress testing” subsection with CLI example and deliverable paths.
- [x] `evals/stress/README.md`: scenario descriptions, fixture regeneration, metric budgets.
- [x] `docs/technical/cag-stress-testing.md`: full process, structures, classes, decisions (KB).
- [x] `docs/arquitectura-estimador-cag.html` § CAG stress testing: illustrated guide with diagrams.
- [ ] Second Brain session note (user-driven): learning reflections on silent degradation vs hard failures.

## Implementation Plan

Execute **strictly in order**; do not start step N+1 until step N is COMPLETE and validated.

- [ ] **Step 1 — Inspect and map:** Confirm file map in this document; no code edits.
- [ ] **Step 2 — `turn_observed`:** Add aggregated log event on session estimate success.
- [ ] **Step 3 — Retrievable observation:** `Session.last_turn_observation` + `SessionDetailResponse` extension.
- [ ] **Step 4 — Scenarios:** `evals/stress/scenarios.py` with three families × five N values.
- [ ] **Step 5 — PDF fixtures:** `evals/stress/fixtures/build_pdfs.py` (+ dev dep if needed).
- [ ] **Step 6 — Metrics:** `evals/stress/metrics.py` with three deterministic metrics.
- [ ] **Step 7 — Metric tests:** `tests/test_stress_metrics.py`.
- [ ] **Step 8 — Runner:** `evals/stress/run.py` → `evals/stress/results.csv`.
- [ ] **Step 9 — Report:** Generate `evals/stress/REPORT.md` from CSV.
- [ ] **Step 10 — Final verification:** Complete checklist; list changed files and caveats.

### Per-step response template (for `/start-task` execution)

```text
STEP X — <title>
Objective / Files / Plan / Implementation / Validation / Status (COMPLETE | BLOCKED)
```

## Learnings

### Pitfalls from codebase vs exercise assumptions

1. **Wrong entrypoint:** Wiring `turn_observed` into `ConversationalEstimationService` would miss all real traffic.
2. **Phantom fields:** Emitting fake non-zero `anchors_count` or tier values would corrupt cross-run comparisons; use honest defaults.
3. **Log parsing fragility:** Stdout log scraping breaks in-process tests and CI; session debug field is the robust path.
4. **Silent degradation:** Existing `tests/evals` check schema and judge quality, not monotonic cost growth or fact recall vs turn depth — that is the point of this feature.
5. **Attachment stress vs turn stress:** Same runner loop covers both dimensions; keep attachment transcript constant when isolating size variable.
6. **`dev_mode` split:** If observation is stored server-side in FR-02, runner does not depend on client-visible usage fields.

### Design choices (defaults)

| Choice | Decision | Rationale |
| --- | --- | --- |
| Observation retrieval | `GET /sessions/{id}` field | Deterministic, testable |
| Metrics module location | `evals/stress/metrics.py` | Stress-specific inputs; avoids coupling to pytest eval package |
| Missing anchors/tier | `0` / `"default"` | Preserves CSV schema without inventing subsystems |
| Cache kind | `semantic` \| `none` only on session path | Matches `StructuredPipelineOutcome.cached` |
| PDF library | `fpdf2` dev dependency | Minimal API; `pypdf` cannot write |
| Default budgets | `4000 ms`, `$0.05` per turn | Exercise SLA examples; override via CLI |

## Environment Variables

Stress runs against real LLM require existing estimator credentials (no new secrets):

| Variable | Required for | Notes |
| --- | --- | --- |
| `OPENAI_API_KEY` | HTTP stress with OpenAI | Default provider |
| `DEV_MODE` | Optional | Expose usage in estimate JSON |
| `SEMANTIC_CACHE_ENABLED` | Optional | Document in REPORT if disabled |

No new env vars required for core deliverable.

## Estimation

- Size: L
- Estimated time: 4–6 hours
- Planned steps: 8 (maps to implementation plan steps 2–10; step 1 complete in this document)

| Step | Effort |
| --- | --- |
| 2–3 Observation + debug | Small |
| 4–5 Scenarios + PDFs | Small |
| 6–7 Metrics + tests | Small |
| 8 Runner | Medium |
| 9 Report | Small |
| 10 Verification + docs | Small |

## Implementation progress

- [x] Step 1 — Inspect and map (complete in Context §)
- [x] Step 2 — `turn_observed` builder + logging
- [x] Step 3 — Retrievable observation on GET session
- [x] Step 4 — Scenarios (`evals/stress/scenarios.py`)
- [x] Step 5 — PDF fixtures (`build_pdfs.py`)
- [x] Step 6 — Metrics (`evals/stress/metrics.py`)
- [x] Step 7 — Metric unit tests
- [x] Step 8 — Runner CLI
- [x] Step 9 — REPORT generation
- [x] Step 10 — Final verification + README (automated; E2E HTTP run manual)

## Pull Request

- Draft: https://github.com/povedica/master-ia-lidr/pull/24
- Branch: `feature/029-cag-stress-testing`

## Repository commits (master-ia)

| Commit | Summary |
| --- | --- |
| docs(work-item) | Add feature-029 CAG stress testing spec |
| feat(sessions) | Add turn_observed logging and session debug field |
| feat(stress) | Add scenarios, metrics, report, and PDF fixtures |
| feat(stress) | Add CLI runner and document stress workflow |
| docs(stress) | Add sample `growing` scenario results.csv and REPORT.md from local HTTP run |
