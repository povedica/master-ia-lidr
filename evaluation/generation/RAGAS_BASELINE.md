---
tolerance: 0.05
metrics:
  faithfulness: 0.5692914979757084
  answer_relevancy: null
  context_precision: 0.8633333332892222
  context_recall: 0.14
---

# RAGAS Generation Baseline

Committed regression baseline for `app/scripts/ragas_generation_eval.py --gate`.

## Provenance

- Seeded from run `evaluation/generation/results/20260629T185540Z/` (5-query
  `evaluation/generation/golden_set.json`, feature-052 finite-metrics fix).
- `answer_relevancy` is `null` because every query in that run produced a
  non-finite (`NaN`) per-query score; the gate skips any metric whose
  baseline or current mean is not finite (see `evaluate_gate()` in
  `app/embedding_pipeline/generation_eval.py`).
- `context_precision` and `context_recall` are documented here for context
  but are **not** gated in this slice (FR-01 only gates `faithfulness` and,
  when finite, `answer_relevancy`).

## Tolerance

- Default tolerance: **0.05** (absolute, on the 0–1 metric scale).
- A run regresses when `current_mean < baseline_mean - tolerance` for a
  gated metric.
- Override per-invocation with `--tolerance <float>`; override the baseline
  file with `--baseline <path>`.

## Updating this baseline

Only update the front matter above after a deliberate, reviewed run:

1. Run `uv run python app/scripts/ragas_generation_eval.py` (writes a fresh
   `evaluation/generation/results/<timestamp>/metrics.json`).
2. Review `comparison.md` and `quality_note.md` for the new run; confirm the
   change is an intentional improvement (or an accepted regression), not
   noise.
3. Copy the new `mean.*` values from `metrics.json` into the `metrics:` block
   above and note the source timestamp in **Provenance**.
4. Do not commit the `evaluation/generation/results/<timestamp>/` directory
   itself; only this baseline file is version-controlled.
