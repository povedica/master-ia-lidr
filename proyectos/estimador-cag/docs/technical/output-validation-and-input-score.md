# Output validation vs API `score`

This project mirrors `ai-engineering/estimator`: Level-1 structural scoring runs in the **HTTP router** when evaluation is enabled (default), not inside the LLM orchestration service.

## `score` and `structure_evaluation` (when `evaluate: true`, default)

- **What it measures:** Level-1 **structure of the generated markdown** (not the transcription).
- **How:** `evaluate_estimation_structure()` in `app/services/evaluation.py` — same checks and formula as `ai-engineering/estimator` `app/services/evaluation.py` (title, Task/Hours/Cost table, totals, team, duration, row vs declared totals, `finish_reason` allowlist). Score is the mean of boolean gates, **rounded to 3 decimals** — same as `EstimationResponse.validation.score` in the reference repo.
- **When:** Request field `evaluate` defaults to `true`. Set `evaluate: false` to omit `score`, `structure_evaluation`, and `output_validation` from the JSON (stats logging still computes the structural score when `ESTIMATION_STATS_LOG_ENABLED` is on).

Adaptive routing still uses input signals internally (`RequestAssessment`, `assess_and_select_mode`, etc.); that input-quality scalar is **not** exposed as `score` on the wire.

## `output_validation` (optional, with `evaluate: true`)

- **What it measures:** **Mode-specific** required sections and aggregate structure for the active `basic` / `standard` / `professional` / `expert_review` profile.
- **When:** Returned when the client leaves `evaluate` at default `true` or sets `evaluate: true`.
- **How:** `evaluate_estimation_output()` in `app/services/estimation_output_validation.py` uses `required_section_presence()`, `validate_mode_output()`, and `{stop, end_turn}` for `finish_reason`. It does **not** define a second numeric “score”; use top-level `score` / `structure_evaluation` for the estimator-compatible metric.

## `finish_reason` (DEV / stats)

- **What it is:** Provider stop reason (`finish_reason` from OpenAI chat completions, `stop_reason` mapped into the same field for Anthropic).
- **When:** Included in JSON when `DEV_MODE=true`, and in NDJSON stats lines when stats logging is enabled.

## Preprocessing (`preprocessing` request field)

- **`none`:** Single LLM pass (default).
- **`inline_cleaning`:** Adds meeting-cleaning instructions to the system prompt (no extra LLM call).
- **`two_phase`:** Runs an extraction LLM call first (any non-`static_fallback` provider in the chain), then the main estimation call. Phase-one prompt/output tokens are accumulated into `usage.preprocessing_input_tokens` / `usage.preprocessing_output_tokens` on top of any SDK-reported preprocessing counters from the main call.
