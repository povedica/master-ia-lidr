# Feature: Remove unused EstimationRequest fields from prompt contract

## Objective

Remove structured form fields from `EstimationRequest` and from estimation prompts when they are not collected by the current simplified session UI and only add noise (empty defaults, derived placeholders, or misleading scope sections). The LLM should infer integrations, risks, data sensitivity, out-of-scope items, and similar details from the free-text transcript and description when they appear there.

## Context

- The simplified session flow (`POST /api/v1/sessions/{session_id}/estimate`) adapts `SessionEstimateRequest` into `EstimationRequest` via `app/services/simplified_session_adapter.py`.
- Previously, the adapter and guided-form contract carried many fields from the legacy guided UI (`feature-008`) that are no longer exposed in the product.
- `deliverables` was especially harmful: the adapter synthesized 3–8 truncated transcript chunks that looked like scope bullets but were not semantically valid.
- LLM call audit JSON (`feature-027`) showed prompt variables such as `data_sensitivity: regulated_unknown`, empty integration lists, and null delivery metadata on every simplified submit.

## Scope

### Includes

- Remove from `EstimationRequest`, prompt rendering, semantic cache surfaces, tests, README examples, and frontend validation mappings:
  - `deliverables` (prior step in same initiative)
  - `out_of_scope`
  - `target_date`
  - `delivery_approach`
  - `integration_categories` / `integration_custom_names`
  - `data_sensitivity`
  - `hosting_constraints` / `hosting_notes`
  - `team_context`
  - `ui_languages`
  - `risk_level`
  - `external_dependencies`
  - `delivery_urgency`
- Remove related Jinja sections from `guided_request.md.j2` (v1 and v2), including **Entrega y plazos**.
- Remove derived `_derive_deliverables()` from the simplified session adapter.
- Slim semantic cache bucket hashing and vector text to remaining structured fields.
- Update `feature-020` references that assumed derived deliverables or explicit sensitivity/urgency warnings from removed fields.

### Excludes

- Removing `detail_level` or `output_format` (still used as estimation preferences with session defaults).
- Re-adding any of the removed fields to the simplified UI in this work item.
- Changing `EstimationResult` output schema.

## Functional requirements

### FR-01: Slim request contract

`EstimationRequest` keeps only fields that the current product collects or that the session adapter sets intentionally:

| Field | Role |
|-------|------|
| `project_name`, `project_summary`, `project_type`, `target_audience`, `target_audience_other` | Product context |
| `industry`, `industry_other` | Optional sector |
| `project_description` | Primary narrative (transcript + extras + attachment context in session flow) |
| `detail_level`, `output_format` | Estimation preferences (session defaults: medium / phases_table) |
| `attachments`, `preprocessing`, `evaluate` | Attachments and pipeline flags |

### FR-02: Prompt surface

The guided user message must contain:

- Product context
- Project description
- Output preferences
- Attachment notes (when attachments exist)

It must **not** render empty or placeholder sections for integrations, data sensitivity, hosting, risks, out-of-scope lists, or synthetic deliverables.

### FR-03: Session adapter

`adapt_to_estimation_request()` maps only explicit session fields plus internal defaults for output preferences. It must not infer or fabricate scope lists, compliance metadata, or delivery urgency.

## Technical approach

1. Delete fields and validators from `app/schemas/estimation_request.py`; remove unused enums (`DataSensitivity`, `IntegrationCategory`, etc.).
2. Simplify `build_request_render_context()` and `build_assessment_chunks()` in `app/services/prompt_context.py`.
3. Trim `guided_request.md.j2` partials (v1/v2).
4. Update `semantic_cache/bucket.py` bucket payload and vector text.
5. Adjust tests, fixtures, `README.md`, `validationErrors.ts`, and dump/stress scripts.

## Acceptance criteria

- [x] AC-01: Removed fields are absent from `EstimationRequest` OpenAPI schema.
- [x] AC-02: Simplified session submits no longer populate removed variables in LLM audit `variables_before_render`.
- [x] AC-03: Guided prompt has no **Entregables**, **Integraciones y datos**, **Restricciones y entorno**, or **Riesgos** sections unless reintroduced later with real inputs.
- [x] AC-04: Assessment surface chunks are `project_summary` + `project_description` only.
- [x] AC-05: Python and web unit tests updated; full backend suite green.

## Test plan

- `uv run pytest tests/test_estimation_request.py tests/test_estimation_request_render.py tests/test_simplified_session_adapter.py tests/test_semantic_cache_bucket.py`
- `uv run pytest` (full suite)
- `npm test -- --run src/features/estimation/lib/validationErrors.test.ts`

## Verification

| Check | Result |
|-------|--------|
| Backend unit/integration tests | **Verified** — `uv run pytest`: 284 passed, 9 skipped |
| Frontend validation mapping tests | **Verified** — Vitest on `validationErrors.test.ts` |
| Manual LLM audit JSON inspection | **Verified** — simplified session submits show slim `variables_before_render` without removed fields |
| Residual risk | Clients sending removed JSON fields receive 422 extra-field errors until updated |

## Docs impact

- `README.md` curl example updated
- This work item (`feature-028`)
- `feature-020-simplified-session-estimation-metadata.md` cross-reference updated

## Repository commits (master-ia)

| Commit | Summary |
|--------|---------|
| `11bbbf4` | `feat(llm): persist provider calls as JSON audit files` — prerequisite audit surface used to diagnose prompt noise (`feature-027`) |
| `eaf1818` | `refactor(estimation): remove unused guided-form fields from request and prompts` — schema, adapter, Jinja partials, semantic cache, tests, frontend validation |
| `cf7998d` | `docs(feature-028): record verification and implementation commits` — completion section for this work item |
