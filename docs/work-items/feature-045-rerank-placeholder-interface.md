# Feature: Rerank Placeholder Interface (NoOp) + Signals

> Sub-feature 4 of 7 of the epic `feature-041-retrieval-debug-observability-screen`.
> Depends on: `feature-044` (fusion produces the input order a reranker would reorder).
> Internal tooling. Not user-facing.

## Why this sub-feature

Reranking is the most likely future improvement to retrieval quality, but a real reranker (cross-encoder or LLM-as-reranker) is costly and out of scope now. If we don't fix the contract early, adding it later forces breaking changes across the API, the diff, the explanation engine, and the (later) UI. This sub-feature locks the rerank contract and a visible rerank lane today with zero behavior risk, so a real reranker becomes a drop-in.

## Objective

Introduce a `Reranker` protocol with a `NoOpReranker` implementation, wire a rerank step into the debug orchestrator that runs after fusion, and surface `rerank_score`/`rerank_rank`, `diff.dropped_by_rerank`, and the `rerank_promoted`/`rerank_demoted` signals — all as a transparent no-op until a real model is configured.

## Value increment (what ships and why it matters)

- `rerank.enabled=true` returns a rerank lane that, with no real model, preserves input order and is clearly flagged as a no-op in `warnings`.
- The response, diff, and explanation already account for rerank promotion/demotion/drops.
- Result: the contract and UI semantics for reranking are final; future real-reranker work is purely an implementation swap (`Reranker` impl) with no contract change.

## SMART framing

- **Specific:** one protocol + one NoOp impl + orchestrator step + signal/diff wiring.
- **Measurable:** AC-01…AC-08; no-op preserves order; warning emitted; signals reserved.
- **Achievable:** small, pure interface; no model, no I/O.
- **Relevant:** future-proofs the most impactful retrieval extension.
- **Time-boxed:** Size S, ~4 baby steps.

## Context

- After `feature-044`, the orchestrator produces a fused (or single-branch) ordered list. The reranker consumes that ordered list and returns a (possibly reordered) list with scores.
- Schemas already reserve `rerank_score`/`rerank_rank` (nullable), `branches.rerank`, `diff.dropped_by_rerank`, and the `rerank_promoted`/`rerank_demoted` vocabulary (extend if missing).

## Handoff from feature-044

Feature-044 shipped hybrid rank fusion for the internal retrieval debug API on branch `feature/044-hybrid-fusion-ranking-diff-explanation` and PR `#40`.

Shipped interfaces:

- `POST /api/v1/retrieval-debug` now accepts `hybrid` config with `enabled`, `method: "rrf"|"weighted"`, `rrf_k`, and optional branch `weights`.
- `strategies` can include `hybrid`; `strategies: ["all"]` resolves to vector, lexical, hybrid, and future rerank warning.
- `branches.hybrid[]` exposes fused rank entries with `rank`, `chunk_id`, `document_id`, and `score`.
- Hybrid `final_results[]` are ordered by `fusion_rank`, capped by `max_results`, and include `fusion_score`, semantic evidence, lexical evidence, `source_strategies`, metadata, excerpt, and controlled explanations.
- `diff` now reports `common`, `vector_only`, `lexical_only`, `hybrid_rescued`, `big_movers`, `dropped_by_threshold`, and `dropped_by_rerank`.

Changed contracts:

- `RetrievalDebugRequest` includes `hybrid`; `method="weighted"` without weights returns `422`.
- `DebugResult` includes nullable `fusion_score` and `fusion_rank`.
- `RetrievalDebugResponse` includes nullable `diff`; it is present for enabled hybrid responses and `null` for vector/lexical-only or disabled hybrid fallback.
- `timings_ms` includes a `hybrid` key.
- Controlled explanation signals are centralized in `app/embedding_pipeline/fusion.py`.

Verification evidence:

- `uv run pytest tests/embedding_pipeline/test_fusion.py -q` — passed during Steps 1–3.
- `uv run pytest tests/embedding_pipeline/test_retrieval_debug_schemas.py -q` — `23 passed`.
- `uv run pytest tests/embedding_pipeline/test_fusion.py tests/embedding_pipeline/test_retrieval_debug_schemas.py tests/embedding_pipeline/test_retrieval_debug_service.py -q` — `35 passed`.
- `uv run pytest tests/embedding_pipeline -q` — `180 passed, 2 deselected`.
- `uv run pytest` — `571 passed, 11 skipped, 12 deselected`.

Not verified:

- Live Compose/Postgres curl smoke for `strategies: ["vector", "lexical", "hybrid"]`, `"all"`, weighted config, and `enabled=false`.
- Rerank behavior; `dropped_by_rerank` remains empty for feature-045.

Residual risks:

- Hybrid rescue and big-mover thresholds are deterministic constants in the service; future UI work may tune them after real corpus inspection.
- RRF scores are intentionally raw RRF contributions, while weighted fusion scores are normalized weighted sums; docs describe both, but UI labels should avoid comparing them as the same scale.

Recommended first tests for feature-045:

- Add rerank placeholder tests that consume existing `branches.hybrid`, preserve `diff.dropped_by_rerank`, and verify `rerank_*` signals remain controlled.
- Re-run `uv run pytest tests/embedding_pipeline/test_fusion.py tests/embedding_pipeline/test_retrieval_debug_service.py -q` before adding any rerank behavior.

## Scope

### Includes

- `app/embedding_pipeline/rerank.py`:
  - `Reranker` protocol: `async def rerank(query: str, candidates: list[RerankCandidate]) -> list[RerankedItem]` (stable signature).
  - `NoOpReranker`: returns candidates in input order with `rerank_score=None` (or pass-through score) and no drops; declares `is_noop = True`.
- Orchestrator step in `retrieval_debug.py`: when `rerank.enabled`, run the configured reranker (default `NoOpReranker`) over the fused/ordered list; populate `branches.rerank`, `rerank_score`/`rerank_rank` on `final_results`, reorder final list if the reranker changes order, compute `diff.dropped_by_rerank`, and add `rerank_promoted`/`rerank_demoted`/(no-op) signals.
- `warnings` entry when `rerank.enabled=true` and the active reranker `is_noop` (e.g. `"rerank.enabled=true but no reranker configured; rerank is a no-op placeholder"`).
- Settings/DI hook so a future real reranker can be injected without touching the router.
- Unit + service tests.

### Excludes

- Any real reranker model or provider call (explicit follow-up in epic `Future Extensions`).
- Metadata filters (046), frontend (047), indexed FTS (048).

## Functional Requirements

### FR-01 — Rerank config

`rerank` = `{ "enabled": bool }` (default `false`). When `false`, no rerank lane; `branches.rerank=null`; rerank fields on results are `null`.

### FR-02 — No-op behavior

With `enabled=true` and `NoOpReranker`: `final_results` order is unchanged from the fused/branch order; `rerank_rank` equals input position; `rerank_score` is `null` (or pass-through); `diff.dropped_by_rerank=[]`; a clear `warnings` entry is present.

### FR-03 — Future-real contract (modeled, not implemented)

The response must already represent a real reranker's effects so no schema change is needed later: a reranker that reorders sets `rerank_rank` ≠ input order and triggers `rerank_promoted`/`rerank_demoted` signals on affected results; one that filters populates `diff.dropped_by_rerank`. These paths are covered by tests using a **fake** reordering reranker (not a real model).

### FR-04 — Injection

The active `Reranker` is resolved via DI/settings; the router never constructs a model. Default is `NoOpReranker`.

## Technical Approach

- `Reranker` is a `typing.Protocol`; `NoOpReranker` is the default binding.
- Orchestrator runs rerank strictly after fusion/ordering; recompute `final_position` from rerank order when a reranker reorders.
- A `FakeReorderReranker` lives in tests/fakes to exercise FR-03 deterministically.

## Acceptance Criteria

- [ ] AC-01: `Reranker` protocol and `NoOpReranker` exist with the documented async signature.
- [ ] AC-02: `rerank.enabled=false` → no rerank lane; rerank fields `null`; `branches.rerank=null`.
- [ ] AC-03: `rerank.enabled=true` with `NoOpReranker` preserves fused order; `rerank_rank`=input order; `diff.dropped_by_rerank=[]`.
- [ ] AC-04: A `warnings` entry clearly flags the no-op placeholder when rerank is enabled with no real model.
- [ ] AC-05: With a fake reordering reranker, `final_results` reorder, `rerank_rank` updates, and `rerank_promoted`/`rerank_demoted` signals appear correctly.
- [ ] AC-06: With a fake filtering reranker, dropped chunks appear in `diff.dropped_by_rerank`.
- [ ] AC-07: The active reranker is injected via DI/settings; the router constructs no model.
- [ ] AC-08: Default suite passes offline; docs describe the rerank contract and no-op semantics.

## Test Plan

- Unit: `NoOpReranker` identity behavior; `FakeReorderReranker`/`FakeFilterReranker` effects on order, signals, and drops.
- Service: orchestrator runs rerank after fusion; no-op warning emitted; reorder/filter paths update final positions and diff.
- Manual: curl debug `rerank.enabled=true` → confirm unchanged order + warning.

## Verification

- Automated: `uv run pytest tests/embedding_pipeline -q`.
- Manual: curl debug with rerank toggled; inspect warning + rerank fields.
- Not verified yet: real reranker quality/latency (future extension).

## Documentation Plan

- `docs/technical/README.md`: rerank protocol, no-op semantics, how a real reranker plugs in, signals/diff handling.
- `README.md`: rerank toggle note (placeholder) in internal-tools section.
- Second Brain: short note on why the contract is fixed before the model.

## Implementation Plan

- [ ] Step 1: `rerank.py` (`Reranker` protocol + `NoOpReranker`) + unit tests.
- [ ] Step 2: Add fake rerankers in tests/fakes (reorder + filter) + unit tests for signals/drops.
- [ ] Step 3: Wire rerank step + DI/settings into `retrieval_debug.py`; populate fields/diff/warnings + service tests.
- [ ] Step 4: Docs sweep + manual verification.

## Estimation

- Size: S
- Estimated time: 3 hours
- Planned steps: 4
- Depends on: feature-044
- Unblocks: feature-047 (rerank UI lane)

## Implementation progress

- Draft PR: https://github.com/povedica/master-ia-lidr/pull/41
- [x] Step 1: Reranker protocol and NoOpReranker contract.
- [x] Step 2: Rerank request/result schema contract.
- [ ] Step 3: Debug orchestrator rerank step with no-op, reorder, and filter test doubles.
- [ ] Step 4: Documentation sweep and final verification.

Verified after Step 1:

- `uv run pytest tests/embedding_pipeline/test_rerank.py::test_noop_reranker_preserves_input_order_and_sets_ranks -q` — RED failed first with missing `app.embedding_pipeline.rerank`, then passed after implementation.
- `uv run pytest tests/embedding_pipeline/test_rerank.py -q` — passed.

Verified after Step 2:

- `uv run pytest tests/embedding_pipeline/test_retrieval_debug_schemas.py::test_retrieval_debug_request_accepts_rerank_config_defaults tests/embedding_pipeline/test_retrieval_debug_schemas.py::test_debug_result_accepts_rerank_fields -q` — RED failed first with missing `RerankBranchConfig`, then passed after implementation.
- `uv run pytest tests/embedding_pipeline/test_retrieval_debug_schemas.py -q` — passed.

## Start-task plan

### Step 1: Reranker contract

**Goal:** Add the pure reranker interface and default no-op implementation.
**Changes:** `app/embedding_pipeline/rerank.py`, `tests/embedding_pipeline/test_rerank.py`.
**TDD:** RED with `tests/embedding_pipeline/test_rerank.py::test_noop_reranker_preserves_input_order_and_sets_ranks`, then GREEN with the minimal protocol/implementation.
**Verification:** `uv run pytest tests/embedding_pipeline/test_rerank.py -q`.
**Documentation:** Mark Step 1 in `## Implementation progress`.
**Suggested commit:** `feat(retrieval): add noop reranker contract`.

### Step 2: Rerank schema contract

**Goal:** Expose `rerank.enabled`, `rerank_score`, and `rerank_rank` without changing disabled behavior.
**Changes:** `app/embedding_pipeline/retrieval_debug_schemas.py`, `tests/embedding_pipeline/test_retrieval_debug_schemas.py`.
**TDD:** RED with `tests/embedding_pipeline/test_retrieval_debug_schemas.py::test_retrieval_debug_request_accepts_rerank_config_defaults`, then GREEN with the minimal schema additions.
**Verification:** `uv run pytest tests/embedding_pipeline/test_retrieval_debug_schemas.py -q`.
**Documentation:** Mark Step 2 in `## Implementation progress`.
**Suggested commit:** `feat(retrieval): expose rerank debug contract fields`.

### Step 3: Rerank orchestration

**Goal:** Run rerank after fusion/ordering, support DI, emit no-op warning, branch entries, final-result ranks, promotion/demotion signals, and rerank drops.
**Changes:** `app/embedding_pipeline/retrieval_debug.py`, `app/embedding_pipeline/fusion.py`, `tests/embedding_pipeline/test_retrieval_debug_service.py`.
**TDD:** RED with service tests for no-op preservation, fake reorder promotion/demotion, and fake filter drops; then GREEN through the smallest service wiring.
**Verification:** `uv run pytest tests/embedding_pipeline/test_retrieval_debug_service.py -q` and `uv run pytest tests/embedding_pipeline/test_fusion.py tests/embedding_pipeline/test_retrieval_debug_schemas.py tests/embedding_pipeline/test_retrieval_debug_service.py -q`.
**Documentation:** Mark Step 3 in `## Implementation progress`.
**Suggested commit:** `feat(retrieval): wire rerank placeholder into debug service`.

### Step 4: Documentation and final verification

**Goal:** Document no-op rerank semantics and verify the embedding pipeline regression set.
**Changes:** `README.md`, `docs/technical/README.md`, this work item, and Second Brain note if applicable.
**TDD:** Exception: documentation/manual smoke only; no new production logic.
**Verification:** `uv run pytest tests/embedding_pipeline -q`; manual curl for `rerank.enabled=true` when local API/Postgres are available.
**Documentation:** Mark Step 4, update acceptance/verification evidence, and record PR URL.
**Suggested commit:** `docs(retrieval): document rerank placeholder contract`.

## Repository commits (master-ia)

| Commit | Summary |
| --- | --- |
| `9296ed3` | Planned the rerank placeholder task, estimation, progress tracking, and TDD verification steps. |
| `cf35559` | Recorded the draft PR link and initialized the repository commit report. |
| `1e7d6c0` | Added the `Reranker` protocol, `NoOpReranker`, rerank candidate/result value objects, and unit coverage for no-op identity behavior. |
| `1c256d2` | Recorded the no-op reranker implementation commit in the work item. |
| `70f6e21` | Added `rerank.enabled`, nullable result rerank fields, and schema tests for the rerank debug contract. |
