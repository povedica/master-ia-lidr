# Feature: RAGAS Eval Gate and Monitor (Phase 1 parity)

## Objective

Extend the offline RAGAS generation harness (`app/scripts/ragas_generation_eval.py`) with **CI-friendly regression gating** aligned with the official master (`eval_generation_s11.py --gate`, `--monitor`):

1. `--gate` — compare aggregate metrics against a committed baseline with tolerance; exit non-zero on regression.
2. `--monitor` — print faithfulness + answer relevancy summary for watch mode.
3. Baseline template at `evaluation/generation/RAGAS_BASELINE.md` with means and tolerance knobs.

This is **child slice Step 3** of `docs/work-items/feature-053-official-master-parity-alignment.md`. It does not change the RAG HTTP API or retrieval pipeline.

## Context

### Official reference

| Artifact | Official path | Behavior |
| --- | --- | --- |
| Generation gate | `estimator/scripts/eval_generation_s11.py` | `--gate`, `--monitor`, `--baseline`, tolerance, exit codes |
| Baseline doc | `estimator/evals/RAGAS_BASELINE_S11.md` | Committed means + tolerance |

### `master-ia` fork choices

- Reuse `app/embedding_pipeline/generation_eval.py` for metric aggregation and JSON-safe floats (feature-052).
- Gate logic stays **deterministic in unit tests** via injected metrics; live RAGAS runs remain `@pytest.mark.slow`.
- Do not commit `evaluation/generation/results/` artifacts; baseline lives in `RAGAS_BASELINE.md` only.

### Parent roadmap

- Depends on: feature-052 (merged).
- Blocks: `feature-058-rag-coherence-and-eval-gate` (coherence + gate integration).

## Scope

### Includes

- `evaluate_gate()` / `load_baseline()` helpers in `generation_eval.py` (or sibling `generation_gate.py` if cleaner).
- CLI flags on `ragas_generation_eval.py`: `--gate`, `--monitor`, `--baseline`, `--tolerance`.
- `evaluation/generation/RAGAS_BASELINE.md` template seeded from run `20260629T185540Z` (finite metrics after feature-052 fix).
- Unit tests for gate pass/fail/missing baseline (mocked metrics, no live RAGAS).
- Update `README.md` eval section with gate usage.

### Excludes

- Live RAGAS in default pytest suite.
- `check_coherence()` (feature-058).
- Named `--config` stage toggles (Phase 2).
- Committing generated `results/` directories.

## Functional Requirements

- **FR-01:** `--gate` loads baseline from `evaluation/generation/RAGAS_BASELINE.md` (or `--baseline` path) and compares `mean_faithfulness` (and optionally `mean_answer_relevancy` when finite).
- **FR-02:** Regression when `current_mean < baseline_mean - tolerance` for any gated metric → exit code **1**; success → **0**; preflight failure → **2** (existing).
- **FR-03:** `--monitor` prints a one-line summary of faithfulness and answer relevancy means without enforcing exit ≠ 0.
- **FR-04:** `--tolerance` overrides default (documented in baseline file, default e.g. `0.05`).
- **FR-05:** Gate functions are pure and unit-testable without importing `ragas` at collection time.
- **FR-06:** `metrics.json` output unchanged except when gate adds a `gate_result` summary object (optional, backward compatible).

## Technical Approach

### Module layout

```text
app/embedding_pipeline/generation_eval.py   # extend: parse baseline, compare metrics
app/scripts/ragas_generation_eval.py        # CLI flags + exit codes
evaluation/generation/RAGAS_BASELINE.md     # committed baseline template
tests/embedding_pipeline/test_generation_gate.py
```

### Baseline file shape (Markdown + YAML front matter or simple table)

Document means for: `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`, plus `tolerance`.

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Eval completed; gate passed (or no `--gate`) |
| 1 | Gate regression |
| 2 | Preflight / runtime error |

## Acceptance Criteria

- [ ] **AC-01:** `uv run python app/scripts/ragas_generation_eval.py --gate` with mocked metrics above baseline exits 0 in unit test.
- [ ] **AC-02:** Same harness with metrics below baseline − tolerance exits 1 in unit test.
- [ ] **AC-03:** `--monitor` prints faithfulness and answer relevancy without changing exit code semantics.
- [ ] **AC-04:** `evaluation/generation/RAGAS_BASELINE.md` exists with documented tolerance.
- [ ] **AC-05:** `uv run pytest tests/embedding_pipeline/test_generation_gate.py` passes without API keys.
- [ ] **AC-06:** Fast suite `uv run pytest` unchanged (no new slow tests in default collection).

## Test Plan

### Unit tests (`tests/embedding_pipeline/test_generation_gate.py`)

- Parse baseline markdown/table.
- Gate pass at baseline mean.
- Gate fail below tolerance.
- Missing baseline file → clear error / exit 2.
- Monitor formatter output (snapshot or substring assert).

### Manual

- `uv run python app/scripts/ragas_generation_eval.py --monitor` with keys (slow, optional).

## Verification

| Check | Command |
| --- | --- |
| Gate unit tests | `uv run pytest tests/embedding_pipeline/test_generation_gate.py -q` |
| Fast suite | `uv run pytest` |
| CLI help | `uv run python app/scripts/ragas_generation_eval.py --help` |

**Not verified at spec time:** live gate against real RAGAS run with API keys.

## Documentation Plan

| Artifact | Update |
| --- | --- |
| `evaluation/generation/RAGAS_BASELINE.md` | New baseline template |
| `README.md` | Gate/monitor CLI examples |
| `feature-053` progress | Step 3 checkbox |

## Implementation Plan

- [ ] **Step 1:** `test_generation_gate.py` RED — baseline parse + compare pure functions.
- [ ] **Step 2:** Implement gate helpers GREEN in `generation_eval.py`.
- [ ] **Step 3:** Wire CLI flags + exit codes in `ragas_generation_eval.py`.
- [ ] **Step 4:** Add `RAGAS_BASELINE.md` + README; mark ACs.

## Estimation

- Size: **S**
- Estimated time: **2 hours**
- Planned steps: **4**

## Implementation progress

- [ ] Step 1: Gate unit tests (RED)
- [ ] Step 2: Gate helpers
- [ ] Step 3: CLI wiring
- [ ] Step 4: Docs + baseline

## Pull Request

- **Branch:** `feature/055-ragas-eval-gate-and-monitor`
- _(URL after WIP PR opened)_

## How to start

```text
/start-task docs/work-items/feature-055-ragas-eval-gate-and-monitor.md
```

Parent: `docs/work-items/feature-053-official-master-parity-alignment.md` Step 3.
