# Feature: RAG Hallucination Gate (Phase 2 parity)

## Objective

Port the official S11 **hallucination gate** into `master-ia`:

1. `numeric_anchor()` — extract verifiable numeric claims from chunks.
2. `judge_estimate()` — batched structured LLM judge comparing lines to anchors.
3. `gate_line()` / `gate_estimate()` — per-line grades (`grounded` / `degraded` / `insufficient`).
4. Integrate after `check_coherence()` in `RagEstimationService` when `HALLUCINATION_GATE_ENABLED=true`.

Extend `RagEstimationResponse` with `HallucinationReport` / per-line grades.

This is **Phase 2 parity** child slice **Step 6** of `docs/work-items/feature-053-official-master-parity-alignment.md`.

## Context

### Official reference

| Artifact | Official path | Behavior |
| --- | --- | --- |
| Hallucination gate | `generation/rag/quality/hallucination.py` | Anchor extraction + judge + aggregate gate |
| Pipeline order | `estimate_from_transcript()` | After coherence, before response |

### `master-ia` fork choices

- New `app/services/rag_hallucination_gate.py`; judge uses `complete_structured` (Instructor), not Responses API.
- Default **off** (`HALLUCINATION_GATE_ENABLED=false`) to avoid surprise LLM cost in dev.
- Runtime toggle via `feature-057` Redis retrieval/model config pattern (stub field OK in this slice).
- Stdlib logging; no `structlog`.
- Unit tests use canned chunks + mocked judge responses (no live LLM in fast suite).

### Parent roadmap

- Depends on: `feature-059` (reformulator + token budget — stable retrieval text into gate).
- Blocks: `feature-062` (stage endpoints include verify stage with hallucination report).
- Parallel with: `feature-061` after `feature-059` merges (different mutex groups).

## Scope

### Includes

- `rag_hallucination_gate.py`: anchor, judge, gate_line, gate_estimate.
- Schemas: `HallucinationLineGrade`, `HallucinationReport`.
- Integration in `RagEstimationService` behind settings flag.
- HTTP response extension (additive).
- Settings: `HALLUCINATION_GATE_ENABLED`, `HALLUCINATION_JUDGE_MODEL`.
- Unit tests: inflated-hours line → `degraded` with canned chunks (AC-11 from feature-053).
- `.env.example` + README.

### Excludes

- Augmentation (`feature-053` FR-10) — separate future slice.
- Synthesis contradiction ranges (`feature-053` FR-22).
- Stage endpoints (`feature-062`).
- React UI for per-line grades (API JSON sufficient).

## Functional Requirements

- **FR-01:** When gate disabled, return empty/neutral report without extra LLM calls.
- **FR-02:** `numeric_anchor()` extracts hour-like numbers and budget references from chunk texts deterministically.
- **FR-03:** `judge_estimate()` batches line items vs anchors via structured LLM (mocked in tests).
- **FR-04:** `gate_line()` returns one of `grounded`, `degraded`, `insufficient` per official semantics.
- **FR-05:** `gate_estimate()` aggregates line grades; `has_degraded` flag on report.
- **FR-06:** Inflated-hours fixture: line with hours >> anchor max → `degraded` in unit test.
- **FR-07:** Citation + coherence stages unchanged; gate runs after coherence.
- **FR-08:** Judge failures log warning and mark line `insufficient` (no unhandled exceptions).

## Technical Approach

### Module layout

```text
app/services/rag_hallucination_gate.py
app/schemas/hallucination_report.py
app/services/rag_estimation_service.py
app/schemas/rag_estimation_response.py
app/config.py
tests/test_rag_hallucination_gate.py
tests/test_rag_estimation_service.py
```

### Pipeline order (after this feature)

```text
... → verify_citations → check_coherence → gate_estimate → response
```

### Settings

```text
HALLUCINATION_GATE_ENABLED=false
HALLUCINATION_JUDGE_MODEL=
```

## Acceptance Criteria

- [x] **AC-01:** Gate disabled → no judge LLM call (mock assertion in service test).
- [x] **AC-02:** Inflated-hours canned fixture → `degraded` line grade.
- [x] **AC-03:** Response JSON includes `hallucination_summary` when gate enabled.
- [x] **AC-04:** `uv run pytest tests/test_rag_hallucination_gate.py -q` passes without API keys.
- [x] **AC-05:** Coherence + citation regression tests pass.
- [x] **AC-06:** `.env.example` documents hallucination settings.

## Test Plan

### Unit tests

- Anchor extraction on fixture chunk texts.
- `gate_line` grades with canned judge output.
- Service integration: enabled vs disabled paths.

### Slow (optional)

- Live judge on one golden query: `@pytest.mark.slow`.

## Verification

| Check | Command |
| --- | --- |
| Hallucination gate | `uv run pytest tests/test_rag_hallucination_gate.py -q` |
| RAG regression | `uv run pytest tests/test_rag_coherence.py tests/test_rag_estimation_service.py -q` |
| Fast suite | `uv run pytest` |

## Documentation Plan

| Artifact | Update |
| --- | --- |
| `.env.example` | Hallucination gate vars ✅ |
| `README.md` | Hallucination report fields ✅ |
| `docs/arquitectura-estimador-cag.html` | Gate stage after coherence ✅ |

## Implementation Plan

- [x] **Step 1:** Schemas + `numeric_anchor()` + `gate_line()` pure logic (TDD).
- [x] **Step 2:** `judge_estimate()` with mocked `complete_structured`.
- [x] **Step 3:** `gate_estimate()` aggregation.
- [x] **Step 4:** Wire service + HTTP response + settings.
- [x] **Step 5:** Docs + architecture HTML.

## Estimation

- Size: **L**
- Estimated time: **5–8 hours**
- Planned steps: **5**

## Handoff from feature-059

`feature-059` adds retrieval prep before generation:

```text
reformulate_query → compose_search_text → retrieve → assemble → truncate_assembled_context → generate → verify_citations → check_coherence
```

**Insert hallucination gate after coherence:**

```text
… → check_coherence → gate_estimate → (response)
```

**Contracts to build on:**

- `RagEstimationOutcome` already carries `coherence_report`; extend with `hallucination_report` without breaking citation/coherence fields.
- `assembled.chunk_texts` and `assembled.chunk_ids` reflect post-truncation context — anchors must use surviving chunks only.
- Settings pattern: follow `RAG_COHERENCE_ENABLED` style; default gate **off**.

**First verification after wiring:**

```bash
uv run pytest tests/test_rag_coherence.py tests/test_rag_estimation_service.py tests/test_rag_estimation_endpoint.py -q
```

## Implementation progress

- [x] Step 1: Schemas + `numeric_anchor()` + `gate_line()` pure logic (TDD)
- [x] Step 2: `judge_estimate()` with mocked `complete_structured`
- [x] Step 3: `gate_estimate()` aggregation
- [x] Step 4: Wire `RagEstimationService` + HTTP response + settings
- [x] Step 5: Docs + `docs/arquitectura-estimador-cag.html`

## Verification (closure)

| Check | Result |
| --- | --- |
| Hallucination gate unit tests | ✅ `uv run pytest tests/test_rag_hallucination_gate.py -q` — 13 passed |
| RAG regression (coherence + service + endpoint) | ✅ 33 passed in targeted run |
| Fast suite | ✅ 746 passed; 2 unrelated `test_config.py` failures from worktree `.env` pollution (`DATABASE_URL`, `RETRIEVAL_RERANK_ENABLED`) |
| `.env.example` / README / architecture HTML | ✅ updated |

**Not verified:** live LLM judge (`@pytest.mark.slow`); Redis runtime toggle for hallucination gate (deferred to feature-062 / runtime config extension).

**Residual risk:** judge prompt quality vs official S11 parity not benchmarked on golden set; numeric `gate_line` may flag lines when anchors are sparse.

## Handoff from feature-060

Shipped interfaces for downstream slices (`feature-062` stage endpoints):

- **Module:** `app/services/rag_hallucination_gate.py` — `numeric_anchor()`, `judge_estimate()`, `gate_line()`, `gate_estimate()`.
- **Schemas:** `app/schemas/hallucination_report.py` — `HallucinationLineGrade`, `HallucinationReport`, judge batch models.
- **Service contract:** `RagEstimationOutcome.hallucination_report` populated after `check_coherence()` on happy and insufficient-context paths.
- **HTTP:** `POST /api/v1/estimate/rag` response adds `hallucination_summary` (`grounded`, `degraded`, `insufficient`, `has_degraded`).
- **Settings:** `HALLUCINATION_GATE_ENABLED` (default `false`), `HALLUCINATION_JUDGE_MODEL` (optional LiteLLM id).
- **Pipeline order:** `… → verify_citations → check_coherence → gate_estimate → response`.

**Recommended first tests for feature-062:**

```bash
uv run pytest tests/test_rag_hallucination_gate.py tests/test_rag_estimation_service.py tests/test_rag_estimation_endpoint.py -q
```

## Repository commits (master-ia)

| SHA | Summary |
| --- | --- |
| `d97f8d2` | test+feat for step 1 — schemas, numeric_anchor(), gate_line() |
| `8dda2c9` | feat: judge_estimate() with batched structured LLM judge |
| `34a7b86` | feat: gate_estimate() aggregation |
| `2c52b9a` | feat: wire hallucination gate into service and HTTP response |
| `028b6dc` | docs: settings, README, architecture HTML, closure + handoff |

## Pull Request

- Merged: https://github.com/povedica/master-ia-lidr/pull/54 (merged 2026-07-07)
- Branch: `feature/060-rag-hallucination-gate` (deleted after merge)
- Parallel manifest: `docs/technical/feature-053-parity-parallel-wave2b.manifest.yaml`

## How to start

```text
/start-task docs/work-items/feature-060-rag-hallucination-gate.md
```

Parent: `docs/work-items/feature-053-official-master-parity-alignment.md` Phase 2 Step 6.
Prerequisite: `feature-059` merged to `main`.
