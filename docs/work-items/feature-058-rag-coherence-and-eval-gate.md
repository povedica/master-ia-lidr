# Feature: RAG Coherence Check and Eval Gate Integration (Phase 1 parity)

## Objective

Close the remaining **Phase 1 S11 foundation** gap after `feature-055` and `feature-057`:

1. Port `check_coherence()` from the official master (`generation/rag/validation.py`) adapted to `RagEstimationResult`.
2. Integrate coherence verification into `RagEstimationService` after `verify_citations()`.
3. Expose coherence summary on `POST /api/v1/estimate/rag` responses.
4. Wire coherence outcomes into the offline eval harness so `--gate` can optionally fail on coherence regressions in golden-set runs.

This is **Phase 1 parity** child slice **Step 4** of `docs/work-items/feature-053-official-master-parity-alignment.md`. It blocks all Phase 2 RAG pipeline work (`feature-059+`).

## Context

### Official reference

| Artifact | Official path | Behavior |
| --- | --- | --- |
| Coherence check | `estimator/app/generation/rag/validation.py:check_coherence()` | Detects internal contradictions across line items (hours, scope, totals) |
| Pipeline order | `estimate_from_transcript()` | `verify_citations` → `check_coherence` → `gate_estimate` |

### `master-ia` fork choices

- Keep `verify_citations()` in `app/services/citation_verification.py`; add `app/services/rag_coherence.py` for semantic coherence (do not mix referential and semantic checks).
- Use stdlib logging with stable `extra` keys (`coherence_check_completed`, `coherence_violation`).
- Coherence is **deterministic** (rule-based / structural); no extra LLM call in this slice.
- Extend `RagEstimationResponse` with a `coherence_summary` view; do not break existing clients (additive fields only).
- Eval gate extension reuses `feature-055` helpers (`load_baseline`, `evaluate_gate`) — no duplicate gate logic.

### Parent roadmap

- Depends on: `feature-055` (RAGAS gate/monitor, merged), `feature-057` (runtime config, merged).
- Blocks: `feature-059-rag-query-reformulator-and-token-budget` and all Phase 2 RAG slices.
- **Not** a dependency of or on `feature-054` (Session 12 agentic loop is a separate track).

### Handoff from feature-055

- `app/embedding_pipeline/generation_eval.py` — gate helpers ready for optional coherence metric.
- Recommended first tests: `check_coherence()` integration with gate exit codes; gate unit tests remain fast and keyless.

## Scope

### Includes

- `app/services/rag_coherence.py` — `check_coherence(estimate, *, request_id) -> CoherenceReport`.
- `app/schemas/coherence_report.py` — line-level status enum, counts, `has_violations`.
- Integration in `RagEstimationService.estimate()` after `verify_citations()`.
- HTTP response extension in `app/schemas/rag_estimation_response.py` and `app/routers/rag_estimations.py`.
- Optional `--coherence-gate` flag on `app/scripts/ragas_generation_eval.py` (or coherence section in gate when golden expectations exist).
- Unit tests with canned incoherent fixtures (deterministic, no LLM).
- `.env.example` + README subsection if a toggle is introduced (default on).
- Update `docs/arquitectura-estimador-cag.html` with coherence stage in RAG flow.

### Excludes

- Hallucination gate (`feature-060`).
- Query reformulation (`feature-059`).
- LLM-judge coherence (official uses structural rules first; judge is hallucination gate).
- React UI changes (coherence summary in API JSON is sufficient for this slice).
- `structlog`.

## Functional Requirements

- **FR-01:** `check_coherence()` flags at minimum: total hours inconsistent with sum of line items beyond tolerance; duplicate/overlapping components; grounded lines with zero hours but non-empty rationale (configurable rules documented in module docstring).
- **FR-02:** `CoherenceReport` mirrors `CitationReport` shape: per-line status, aggregate counts, `has_violations: bool`.
- **FR-03:** `RagEstimationService` always runs coherence after citation verification; insufficient-context path returns empty coherence report.
- **FR-04:** `POST /api/v1/estimate/rag` response includes `coherence_summary` with counts and `has_violations`.
- **FR-05:** Incoherent golden fixture fails `check_coherence()` in unit test without network.
- **FR-06:** Optional eval integration: when `--gate` runs and coherence violations are recorded in metrics, gate may exit non-zero (pure function testable with injected metrics).
- **FR-07:** Layering preserved: `rag_coherence` depends on schemas only; no imports from `embedding_pipeline` in coherence module.
- **FR-08:** Feature-056 regression: API key and rate-limit tests for RAG endpoint still pass.

## Technical Approach

### Module layout

```text
app/services/rag_coherence.py
app/schemas/coherence_report.py
app/services/rag_estimation_service.py   # wire after verify_citations
app/schemas/rag_estimation_response.py   # coherence_summary view
app/routers/rag_estimations.py
app/scripts/ragas_generation_eval.py     # optional coherence gate hook
tests/test_rag_coherence.py
tests/test_rag_estimation_service.py     # extend with coherence assertions
tests/test_rag_estimation_endpoint.py    # response shape
```

### Pipeline order (target)

```text
retrieve → assemble → generate → verify_citations → check_coherence → (response)
```

Hallucination `gate_estimate` remains `feature-060`.

### Coherence rules (port baseline)

Start by porting official structural checks that do not require chunk text:

1. `total_hours` vs sum of `line_items[].hours` (epsilon tolerance, e.g. 0.01).
2. Duplicate `component` names (case-insensitive).
3. `insufficient_context=True` must have empty `line_items` or all zero hours.

Extend with official `validation.py` rules where they map cleanly to `RagEstimationLineItem` fields.

### Settings (optional)

```text
RAG_COHERENCE_ENABLED=true
RAG_COHERENCE_TOTAL_TOLERANCE=0.01
```

When disabled, return a no-op report with `has_violations=false` (documented).

## Acceptance Criteria

- [x] **AC-01:** `check_coherence()` returns `has_violations=true` for a unit-test fixture with mismatched total hours.
- [x] **AC-02:** `RagEstimationService` outcome includes coherence report on happy path and insufficient-context path.
- [x] **AC-03:** `POST /api/v1/estimate/rag` JSON includes `coherence_summary` without breaking existing fields.
- [x] **AC-04:** `uv run pytest tests/test_rag_coherence.py tests/test_rag_estimation_service.py tests/test_rag_estimation_endpoint.py -q` passes without API keys.
- [x] **AC-05:** Feature-055 gate unit tests still pass (`tests/embedding_pipeline/test_generation_gate.py`).
- [x] **AC-06:** Feature-056 security/rate-limit regression tests still pass for RAG route.
- [x] **AC-07:** `.env.example` documents coherence settings if added.
- [x] **AC-08:** `docs/arquitectura-estimador-cag.html` shows coherence step after citation verification.

## Test Plan

### Unit tests

- `test_rag_coherence.py`: each rule in isolation; combined violations; empty estimate.
- `test_rag_estimation_service.py`: mocked LLM returns estimate → coherence report present.
- `test_rag_estimation_endpoint.py`: response schema includes `coherence_summary`.

### Regression

- `uv run pytest tests/test_api_security.py tests/test_api_rate_limiting.py -q`
- `uv run pytest tests/embedding_pipeline/test_generation_gate.py -q`

## Verification

| Check | Command | Result |
| --- | --- | --- |
| Coherence unit tests | `uv run pytest tests/test_rag_coherence.py -q` | **6 passed** |
| RAG service + endpoint | `uv run pytest tests/test_rag_estimation_service.py tests/test_rag_estimation_endpoint.py -q` | **8 passed** |
| Gate regression | `uv run pytest tests/embedding_pipeline/test_generation_gate.py -q` | **19 passed** |
| Security/rate-limit regression | `uv run pytest tests/test_api_security.py tests/test_api_rate_limiting.py -q` | **passed** |
| Feature scope combined | `uv run pytest tests/test_rag_coherence.py tests/test_rag_estimation_service.py tests/test_rag_estimation_endpoint.py tests/embedding_pipeline/test_generation_gate.py tests/test_api_security.py tests/test_api_rate_limiting.py -q` | **41 passed** |
| Full fast suite | `uv run pytest` | **717 passed**, 2 failed (`test_config.py` — local `.env` leaks into `Settings(_env_file=None)`; pre-existing, not introduced by this feature) |
| Live RAGAS + coherence gate | `uv run python app/scripts/ragas_generation_eval.py --gate --coherence-gate` | **Not verified** (requires DB + API keys) |

## Handoff from feature-058

**Shipped interfaces**

- `app/services/rag_coherence.py` — `check_coherence(estimate, *, request_id, enabled=True, total_tolerance=0.01) -> CoherenceReport`
- `app/schemas/coherence_report.py` — `CoherenceReport`, `CoherenceLineReport`, `CoherenceLineStatus`
- `RagEstimationOutcome.coherence_report` — populated after `verify_citations()` on happy and insufficient-context paths
- `POST /api/v1/estimate/rag` — additive `coherence_summary` view (does not break existing fields)
- Settings: `RAG_COHERENCE_ENABLED` (default `true`), `RAG_COHERENCE_TOTAL_TOLERANCE` (default `0.01`)
- Eval: `--coherence-gate` with `--gate` records `coherence_violation_count` in `metrics.json` and may exit `1` via `evaluate_coherence_gate()`

**Pipeline order (current)**

```text
retrieve → assemble → generate → verify_citations → check_coherence → (response)
```

**Recommended first tests for next implementer (`feature-059`)**

```bash
uv run pytest tests/test_rag_coherence.py tests/test_rag_estimation_service.py tests/test_rag_estimation_endpoint.py -q
```

**Not verified:** live golden-set eval with `--coherence-gate`; full `uv run pytest` green in CI without env isolation for `test_config.py`.

**Residual risk:** `RagEstimationResult` validator recomputes `total_hours` from line items on parse — total-hours mismatch is mainly a guard against LLM JSON that bypasses validation; coherence still catches duplicates, insufficient-context shape, and zero-hour grounded lines.

## Pull Request

- **Merged:** https://github.com/povedica/master-ia-lidr/pull/51

## Repository commits (master-ia)

| SHA | Summary |
| --- | --- |
| `8f41f17` | docs(feature-058): add implementation progress and commit log scaffold |
| `9ca65c1` | feat(rag-coherence): add CoherenceReport schema and check_coherence() |
| `c9bdf3e` | feat(rag-estimation): run check_coherence after citation verification |
| `0098ce9` | feat(rag-api): expose coherence_summary on POST /api/v1/estimate/rag |
| `3258e8d` | feat(ragas-eval): add optional coherence gate for golden-set runs |
| `ce7d123` | docs(feature-058): document coherence settings, API field, and eval gate |
| `b6d5090` | docs(feature-058): mark acceptance criteria complete with commit SHAs |

## How to start

```text
/start-task docs/work-items/feature-058-rag-coherence-and-eval-gate.md
```

Parent: `docs/work-items/feature-053-official-master-parity-alignment.md` Phase 1 Step 4.
