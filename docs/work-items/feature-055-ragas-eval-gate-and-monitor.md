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

- [x] **AC-01:** `uv run python app/scripts/ragas_generation_eval.py --gate` with mocked metrics above baseline exits 0 in unit test.
- [x] **AC-02:** Same harness with metrics below baseline − tolerance exits 1 in unit test.
- [x] **AC-03:** `--monitor` prints faithfulness and answer relevancy without changing exit code semantics.
- [x] **AC-04:** `evaluation/generation/RAGAS_BASELINE.md` exists with documented tolerance.
- [x] **AC-05:** `uv run pytest tests/embedding_pipeline/test_generation_gate.py` passes without API keys.
- [x] **AC-06:** Fast suite `uv run pytest` unchanged (no new slow tests in default collection).

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

- [x] **Step 1:** `test_generation_gate.py` RED — baseline parse + compare pure functions.
- [x] **Step 2:** Implement gate helpers GREEN in `generation_eval.py`.
- [x] **Step 3:** Wire CLI flags + exit codes in `ragas_generation_eval.py`.
- [x] **Step 4:** Add `RAGAS_BASELINE.md` + README; mark ACs.

## Estimation

- Size: **S**
- Estimated time: **2 hours**
- Planned steps: **4**

## Implementation progress

- [x] Step 1: Gate unit tests (RED) — `tests/embedding_pipeline/test_generation_gate.py` (14 tests), verified failing on collection before helpers existed.
- [x] Step 2: Gate helpers — `BaselineParseError`, `GenerationBaseline`, `GateMetricComparison`, `GateResult`, `load_baseline`, `evaluate_gate`, `gate_exit_code`, `render_gate_summary`, `render_monitor_summary`, `gate_result_to_json` in `app/embedding_pipeline/generation_eval.py`.
- [x] Step 3: CLI wiring — `--gate`, `--monitor`, `--baseline`, `--tolerance` flags in `app/scripts/ragas_generation_eval.py`; exit 0/1/2 semantics; optional `gate_result` merged into `metrics.json` only when `--gate` is used. Added 2 CLI arg-parsing unit tests.
- [x] Step 4: Docs + baseline — `evaluation/generation/RAGAS_BASELINE.md` seeded from run `20260629T185540Z`; `README.md` gate/monitor usage section; `docs/technical/README.md` §25d "Regression gate and monitor (feature-055)" subsection.

**Verified:**
- `uv run pytest tests/embedding_pipeline/test_generation_gate.py -q` → 16 passed.
- `uv run pytest -q` (fast suite) → 683 passed, 11 skipped, 12 deselected, **2 pre-existing failures** (`tests/test_config.py::test_database_url_defaults_to_empty_string`, `tests/test_config.py::test_retrieval_settings_defaults_are_backward_compatible`) confirmed unrelated to this change — same failures reproduce on the unmodified main worktree due to local `.env` values leaking into `Settings(_env_file=None)` default assertions.
- `uv run python app/scripts/ragas_generation_eval.py --help` shows all four new flags.
- `load_baseline()` manually verified against the real committed `RAGAS_BASELINE.md`.

**Not verified (out of scope / requires live infra):** `--gate`/`--monitor` against a real live RAGAS run with `OPENAI_API_KEY` and populated Postgres (excluded from this slice per Scope; remains a manual follow-up).

## Pull Request

- **Branch:** `feature/055-ragas-eval-gate-and-monitor`
- _(URL after WIP PR opened)_

## Repository commits (master-ia)

| Commit | Summary |
| --- | --- |
| `cc76733` | test(generation-eval): add failing gate/monitor unit tests (RED) |
| `3082d1c` | feat(generation-eval): add RAGAS baseline gate/monitor helpers (GREEN) |
| `104ca23` | feat(ragas-eval): wire --gate/--monitor/--baseline/--tolerance CLI flags |
| `3bddd42` | docs(ragas-eval): add baseline template and gate/monitor usage docs |

## How to start

```text
/start-task docs/work-items/feature-055-ragas-eval-gate-and-monitor.md
```

Parent: `docs/work-items/feature-053-official-master-parity-alignment.md` Step 3.
