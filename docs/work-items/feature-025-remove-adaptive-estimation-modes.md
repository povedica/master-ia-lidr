# Feature: Remove Adaptive Estimation Modes (basic / standard / professional / expert_review)

## Objective

Remove the adaptive estimation mode system (`EstimationMode`: `basic`, `standard`, `professional`, `expert_review`) from the codebase. The product no longer uses discrete routing levels; estimation should follow a single unified path driven by the guided form fields (`detail_level`, `output_format`) and the shared Jinja2 prompt bundle.

This is a **breaking API cleanup** and a **refactor**, not a behavior expansion.

## Context

The adaptive engine was introduced in [`feature-adaptive-estimation-engine.md`](feature-adaptive-estimation-engine.md) and still permeates backend services, settings, few-shot loading, response schemas, semantic cache keys, degraded fallback markdown, and tests.

Related prior work already moved prompt authoring away from four mode-specific bodies:

- [`feature-016-unified-jinja2-prompt-templates-v2.md`](feature-016-unified-jinja2-prompt-templates-v2.md) — one system-instruction partial; `EstimationMode` remained only as a runtime label (token caps, example pool, output checks).
- [`feature-020-simplified-session-estimation-metadata.md`](feature-020-simplified-session-estimation-metadata.md) — session flow no longer depends on the long guided form, but still inherits mode metadata from the shared estimation pipeline.

**Current touchpoints (non-exhaustive inventory):**

| Area | Files / artifacts |
|------|-------------------|
| Core enum + routing | `app/services/estimation_engine.py` (`EstimationMode`, `select_mode`, `ModeEligibility`, `ModeProfile`, mode output validation) |
| LLM orchestration | `app/services/llm_service.py`, `app/guardrails/llm_pipeline.py`, `app/services/llm_chain.py` (degraded markdown per mode) |
| Settings | `app/config.py` — four `ESTIMATION_*_OUTPUT_TOKENS_MAX`, `FORCED_ESTIMATION_MODE`, `completion_token_cap_for_mode()` |
| Few-shot examples | `app/context/examples.py`, `app/context/examples/{basic,standard,professional,expert_review}/` |
| Prompt rendering | `app/services/prompt_context.py`, `app/services/estimation_prompt_rendering.py`, `app/prompts/estimation/v1|v2/partials/system_instructions.md.j2` (`{{ estimation_mode }}`) |
| API schemas | `app/schemas/estimations.py`, `app/schemas/estimation_response.py` — `mode`, `assessment`, `mode_eligibility`, `OutputValidationView.mode` |
| Response builders | `app/services/estimate_response_builder.py`, `app/services/estimation_v2_response_builder.py`, `app/services/estimation_stats_logger.py` |
| Output validation | `app/services/estimation_output_validation.py` (mode-specific required sections) |
| Semantic cache | `app/services/semantic_cache/bucket.py`, `app/services/semantic_cache/artifacts.py` |
| Docs | `README.md` (§ Estimation modes), `docs/technical/README.md` |
| Env | `.env.example` — per-mode token caps and `FORCED_ESTIMATION_MODE` |
| Tests | `tests/test_estimation_engine.py`, `tests/test_config.py`, `tests/test_examples.py`, `tests/test_estimation_output_validation.py`, `tests/test_estimation_stats_logger.py`, `tests/test_providers.py`, plus many tests that pass `EstimationMode.STANDARD` as fixture noise |

**Important distinction — do NOT remove:**

| Concept | Location | Why it stays |
|---------|----------|--------------|
| `DetailLevel` (`summary`, `medium`, `detailed`) | `app/schemas/estimation_request.py` | User-facing guided-form depth; unrelated to `EstimationMode` |
| `OutputFormat` | same | User-facing layout preference |
| `DeliveryUrgency.standard` | same | Unrelated enum value |
| Guardrail id `pii_basic` | `app/guardrails/policy_registry.py` | Unrelated policy name |

## Scope

### Includes

- Delete `EstimationMode` and all adaptive routing / eligibility / mode-profile logic.
- Replace per-mode completion token caps with **one** setting (default **2048**, former `standard` cap).
- Remove `FORCED_ESTIMATION_MODE` and related logging (`estimation_mode_forced`).
- Collapse few-shot examples into a **single flat pool** under `app/context/examples/` (no mode subdirectories).
- Simplify `load_examples()` to sample 2–4 examples from that single pool (no mode argument, no fallback chain).
- Remove `estimation_mode` from prompt render context and from system-instruction templates (line `Estimation profile (routing): {{ estimation_mode }}`).
- Remove API response fields tied to adaptive modes:
  - `mode`
  - `assessment` (`detail_level` / `recommended_mode` / `reason` from the engine)
  - `mode_eligibility` (`allowed_modes`, `blocked_modes`, `reason`)
  - `OutputValidationView.mode` and mode-specific required-section checks
- Replace mode-specific output validation with **Level-1 structure evaluation only** (`evaluate_estimation_structure` / existing `structure_evaluation` and v2 `quality`) or a single unified checklist if Level-1 alone is insufficient — **no mode parameter**.
- Simplify static degraded fallback in `llm_chain.py` to **one** markdown template (based on former `standard` body).
- Remove `estimation_mode` from semantic cache bucket composition; document that existing cache entries become stale (acceptable — cache is optional and off by default).
- Update README, `docs/technical/README.md`, `.env.example`, and relevant Second Brain session notes.
- Delete or rewrite tests that assert mode routing, eligibility, or per-mode validation.

### Excludes

- Changing `DetailLevel` or `OutputFormat` enums or guided-form UX semantics.
- Redesigning the estimation prompt content beyond removing the mode label.
- Frontend changes (no `web/` references to modes today).
- Semantic cache algorithm changes beyond bucket key fields.
- New LLM providers, guardrail policies, or session-store behavior.
- Removing historical work-item documents (`feature-adaptive-estimation-engine.md`, etc.) — they remain as archive; add a short “superseded by feature-025” note only if useful during implementation.

## Functional Requirements

### FR-01: Single estimation path

- Every estimate request (v1 markdown, v2 structured, session estimate) uses the same pipeline prelude: domain guardrail → preprocessing → prompt render → provider call.
- No automatic classification into `basic` / `standard` / `professional` / `expert_review`.
- Depth and layout continue to come from the request (`detail_level`, `output_format`) when the guided form is used, or from session/transcript context otherwise.

### FR-02: Unified completion token cap

- Add `ESTIMATION_OUTPUT_TOKENS_MAX` (default `2048`).
- Remove `ESTIMATION_BASIC_OUTPUT_TOKENS_MAX`, `ESTIMATION_STANDARD_OUTPUT_TOKENS_MAX`, `ESTIMATION_PROFESSIONAL_OUTPUT_TOKENS_MAX`, `ESTIMATION_EXPERT_REVIEW_OUTPUT_TOKENS_MAX`.
- Two-phase preprocessing extraction cap uses `ESTIMATION_OUTPUT_TOKENS_MAX` (or existing dedicated cap if already bounded separately — prefer the unified setting).

### FR-03: Unified few-shot example pool

- Move all usable `.txt` samples into `app/context/examples/` (flat directory).
- `load_examples()` signature becomes parameterless (or accepts only an optional count/rng seed for tests).
- Meeting-summary prefix no longer embeds mode name (e.g. `Historical estimation sample 01.`).
- Bump `EXAMPLES_VERSION` constant when corpus layout changes.

### FR-04: Prompt templates

- Remove `estimation_mode` from `build_prompt_render_context()` / `build_estimation_prompt_context()` and from v1/v2 `system_instructions.md.j2`.
- System instructions continue to reference `detail_level` and `output_format` where the guided form supplies them.

### FR-05: API contract (breaking)

**v1 `EstimateResponse` and v2 `EstimationResponse`:**

- Remove fields: `mode`, `assessment`, `mode_eligibility`.
- When `evaluate=true`, keep `structure_evaluation` / `score` (Level-1). Remove `output_validation` if it only existed for mode-specific section keywords; if retained, it must not reference a mode.

**DEV_MODE metadata:** stop exposing mode-related keys in stats logs and internal debug payloads.

### FR-06: Remove `estimation_engine.py` mode surface

- Delete `EstimationMode`, `InputAssessment`, `ModeEligibility`, `ModeProfile`, `select_mode`, `summarize_assessment`, `evaluate_mode_eligibility`, `enforce_mode_eligibility`, `get_mode_profile`, `validate_mode_output`, `required_section_presence`, and mode routing helpers.
- Delete the module entirely **unless** a small unrelated helper remains worth keeping; prefer deletion and inlining zero replacements.
- Remove `tests/test_estimation_engine.py` or replace with tests for any retained helper (expected: delete file).

### FR-07: Semantic cache bucket

- Remove `estimation_mode` from `build_semantic_cache_bucket()` inputs and serialized artifacts.
- Deserialize path in `artifacts.py` must not expect mode fields.

### FR-08: Static degraded fallback

- `_build_degraded_markdown()` and `_infer_mode_from_system_prompt()` in `llm_chain.py` must not branch on mode.
- One degraded template sufficient for operational continuity when all live providers fail.

### FR-09: Documentation sync

- Remove README § “Estimation modes” table and references to `app/context/prompts/{basic,standard,...}.txt` (legacy paths; verify whether those files still exist and delete if present).
- Update `docs/technical/README.md` adaptive-engine sections and example JSON snippets.
- Update `.env.example` and README environment variable tables.

## Technical Approach

### Settings (`app/config.py`)

```python
estimation_output_tokens_max: int = Field(default=2048, ge=1)
```

Remove `forced_estimation_mode`, `completion_token_cap_for_mode()`, and the four per-mode fields.

### Examples (`app/context/examples.py`)

```python
def load_examples() -> list[EstimationExample]:
    ...
```

Load from `_EXAMPLES_ROOT.glob("*.txt")` after migrating files from `standard/` and `basic/` (dedupe if needed; prefer keeping the richer `standard` corpus, drop redundant `basic` samples unless they add distinct patterns).

### LLM prelude (`llm_service._prepare_call` and v2 pipeline)

Before:

```python
raw_assessment, recommended_mode = assess_and_select_mode(surface)
...
mode = enforce_mode_eligibility(...)
load_examples(mode)
completion_token_cap_for_mode(mode)
```

After:

```python
examples = load_examples()
max_output_tokens = self._settings.estimation_output_tokens_max
# no assessment / mode_eligibility on PreparedCall
```

Update `_PreparedCall`, `EstimationResult` bundles, and guardrail pipeline dataclasses to drop `mode`, `assessment`, `mode_eligibility`.

### Schemas

- Remove `AssessmentView`, `ModeEligibilityView`.
- Trim `OutputValidationView` or delete if Level-1 covers evaluate flows.
- Remove `EstimationMode` imports from all schema modules.

### Output validation

- Delete `app/services/estimation_output_validation.py` if only mode-specific; callers use existing structure evaluation paths.
- Update `tests/test_estimation_output_validation.py` accordingly.

### Tests strategy

- Grep for `EstimationMode`, `recommended_mode`, `allowed_modes`, `FORCED_ESTIMATION_MODE`, `estimation_mode` and fix or delete.
- Keep tests for `load_examples()` random subset behavior with a seeded RNG.
- Keep config tests for the single token cap env override.

## Acceptance Criteria

- [ ] AC-01: `EstimationMode` enum and `app/services/estimation_engine.py` mode routing are fully removed (module deleted or contains no mode concepts).
- [ ] AC-02: No references to `basic`, `standard`, `professional`, or `expert_review` as **estimation modes** remain under `app/` or `tests/` (except archived docs or unrelated enums like `DeliveryUrgency.standard`).
- [ ] AC-03: `.env.example` documents only `ESTIMATION_OUTPUT_TOKENS_MAX`; per-mode caps and `FORCED_ESTIMATION_MODE` are gone.
- [ ] AC-04: Few-shot examples live in a flat `app/context/examples/*.txt` tree; mode subdirectories removed.
- [ ] AC-05: `load_examples()` does not accept a mode parameter.
- [ ] AC-06: System prompt templates no longer render `estimation_mode`.
- [ ] AC-07: v1 and v2 API responses no longer include `mode`, `assessment`, or `mode_eligibility`.
- [ ] AC-08: `OutputValidationView` no longer exposes a mode field (or the view is removed entirely with evaluate flows still working via Level-1).
- [ ] AC-09: Semantic cache bucket JSON excludes `estimation_mode`; artifact round-trip tests pass.
- [ ] AC-10: Static degraded fallback uses a single template.
- [ ] AC-11: `uv run pytest` passes without real API keys.
- [ ] AC-12: README and `docs/technical/README.md` describe a single estimation path (no four-mode table).
- [ ] AC-13: `DetailLevel` / `OutputFormat` on the guided form are unchanged and still flow into prompt rendering.

## Test Plan

### Unit tests

- Config: `ESTIMATION_OUTPUT_TOKENS_MAX` default and env override.
- Examples: flat pool loading, 2–4 random subset, empty pool edge case.
- Prompt rendering: system instructions do not mention “estimation profile (routing)”.
- Response builders: no mode fields in serialized models.
- Semantic cache bucket: stable key without mode dimension.
- LLM chain: single degraded markdown shape.

### Integration tests

- `tests/test_api.py` / v2 observability tests: response JSON schema assertions updated.
- Session estimate tests (`tests/test_simplified_session_router.py`): drop mode fixtures.

### Manual checks

- `uv run uvicorn app.main:app --reload` — POST sample to `/api/v1/estimate` and `/api/v2/estimate`; confirm response has estimation payload without `mode` / `assessment`.
- Optional: with `SEMANTIC_CACHE_ENABLED=true`, confirm a new miss/hit cycle works after bucket change.

## Verification

### Automated

- `uv run pytest`
- Grep gate: `rg -i 'EstimationMode|FORCED_ESTIMATION_MODE|recommended_mode|mode_eligibility|expert_review' app tests --glob '*.py'` returns no hits (allow `DeliveryUrgency` / `pii_basic` false positives only if documented).

### Manual

- Swagger `/docs` — response models match removed fields.
- `.env.example` matches `Settings` fields.

### Not verified yet

- Langfuse / OTEL dashboards that filtered by `mode` tag (update queries separately if used in production).

## Documentation Plan

- `README.md` — remove estimation modes section; update architecture blurb (few-shot no longer “per mode”).
- `docs/technical/README.md` — remove adaptive routing contract JSON; update env var table and directory tree for examples.
- `.env.example` — single token cap.
- Second Brain: add a short note to the latest estimator session doc that adaptive modes were retired (learning note, not canonical work item).

## Implementation Plan

- [ ] Step 1: Add `ESTIMATION_OUTPUT_TOKENS_MAX`, wire through `llm_service` / pipeline; keep old env vars as deprecated no-ops **only if** needed for one release — **preferred: hard remove** per user request.
- [ ] Step 2: Flatten example corpus; simplify `load_examples()`; bump `EXAMPLES_VERSION`; fix `tests/test_examples.py`.
- [ ] Step 3: Remove mode prelude from `llm_service` and `llm_pipeline`; shrink `_PreparedCall` and related bundles.
- [ ] Step 4: Delete `estimation_engine.py` and dependent validation; simplify `llm_chain` degraded path.
- [ ] Step 5: Update schemas, response builders, stats logger, semantic cache artifacts.
- [ ] Step 6: Update prompt context + Jinja2 partials (v1 and v2).
- [ ] Step 7: Fix all tests; run full pytest.
- [ ] Step 8: Sync README, technical docs, `.env.example`.

## Learnings

- **Do not confuse `DetailLevel` with `EstimationMode`.** Removing modes must not break the guided form’s “Profundidad de estimación”.
- **feature-016 already unified prompts.** Most mode complexity left is routing metadata, token caps, example paths, and validation — safe to delete without rewriting prompt prose.
- **Semantic cache keys change.** Expect natural cache miss after deploy; no migration script required.
- **Breaking API change.** Any external client parsing `mode` or `assessment` will break; document in PR / release notes.
- **`tests/test_providers.py`** embeds mode-specific markdown section expectations — rewrite against unified structure, not four profiles.
- Grep for `standard` carefully: many hits are unrelated (`uvicorn[standard]`, `DeliveryUrgency.standard`, guardrail names).

## Estimation

- Size: M
- Estimated time: 3–4 hours
- Planned steps: 8

Medium refactor (~15–25 files). Low runtime risk if tests are updated systematically. Main risk is missing a hidden `mode` reference in observability metadata.

## Implementation progress

- [ ] Step 1: Unified `ESTIMATION_OUTPUT_TOKENS_MAX` in config + tests
- [ ] Step 2: Flatten example corpus; parameterless `load_examples()`
- [ ] Step 3: Remove mode prelude from `llm_service` / `llm_pipeline`
- [ ] Step 4: Delete `estimation_engine.py`, output validation, simplify `llm_chain`
- [ ] Step 5: Schemas, response builders, stats logger, semantic cache
- [ ] Step 6: Prompt context + Jinja2 partials (v1/v2)
- [ ] Step 7: Fix remaining tests; full pytest + grep gate
- [ ] Step 8: Sync README, technical docs, `.env.example`, Second Brain note

## Pull Request

_To be filled during `/start-task`._

## Repository commits (master-ia)

| Commit | Summary |
|--------|---------|
