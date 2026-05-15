# Feature: Humanized guided form validation errors

## Objective

Turn technical validation failures in the guided estimation form into clear, inline, accessible field errors. The immediate user-facing problem is the backend 422 message for custom integrations:

```text
HTTP 422: Value error, each integration_custom_names entry must be at most 40 characters
```

That text must never be shown to end users. The form should instead mark the affected field and show human copy such as:

```text
Cada integración debe ocupar una línea y tener como máximo 40 caracteres.
```

The same error-handling rule applies to every editable input in the guided form: validation failures should be normalized to field-level UI errors whenever the backend or local schema identifies a field.

## Context

- `web/src/features/estimation/components/EstimationWorkbench.tsx` already keeps `fieldErrors`, scrolls/focuses the first invalid field, and uses a `Field` component that can apply `aria-invalid`, `aria-describedby`, a red ring, and inline messages.
- `web/src/features/estimation/lib/requestMapper.ts` already uses Zod for local form validation and contains the custom integrations rule through `findInvalidCustomIntegrationLines`.
- `web/src/features/estimation/hooks/useEstimateStream.ts` currently formats failed HTTP responses as global technical strings via `formatHttpError`, including `HTTP ${status}` and raw FastAPI `detail.msg` values.
- `app/schemas/estimation_request.py` validates `integration_custom_names` and other guided form fields with Pydantic. FastAPI 422 responses expose backend field names and technical messages.
- The affected UI label is `Custom integrations (optional, one per line)` and the backend field is `integration_custom_names`.

## Scope

### Includes

- Normalize local Zod validation errors and backend 422 validation responses into one field-error structure keyed by UI form field names.
- Map backend snake_case fields to existing UI keys, for example `integration_custom_names` -> `integrationCustomText`.
- Apply inline error behavior consistently to all editable guided-form controls, including inputs, selects, multi-selects, textareas, file attachments, and conditional fields.
- Add persistent hint text where it helps prevent errors, starting with custom integrations:
  - `Escribe una integración por línea. Máximo 40 caracteres por línea.`
- Preserve or improve current scroll/focus behavior for the first invalid field, including fields inside the `More details` disclosure.
- Keep global banners as summaries only, for example:
  - `Revisa los campos marcados en rojo.`
- Add tests for local validation, backend 422 normalization, field mapping, and no raw technical leakage.

### Excludes

- Changing backend validation limits or the public `EstimationRequest` contract.
- Adding i18n infrastructure beyond the copy needed for this form.
- Replacing the v2 streaming transport or broader API route migration.
- Redesigning the whole form layout.

## Functional Requirements

### FR-001: Custom integrations local validation

- Split the textarea value by newline.
- Trim each line before validation.
- Ignore empty lines.
- Mark the field invalid when any non-empty line has more than 40 characters.
- Prevent submit while invalid.
- Focus and scroll to the textarea.
- Clear the field error after the content is corrected.

Primary error message:

```text
Cada integración debe ocupar una línea y tener como máximo 40 caracteres.
```

Optional line-specific messages:

```text
La línea 1 supera el máximo de 40 caracteres.
Las líneas 1 y 2 superan el máximo de 40 caracteres.
```

### FR-002: Backend 422 field normalization

When the API returns HTTP 422 and the response contains validation details for a known request field:

- Do not show `HTTP 422`, `Value error`, raw backend field names, or raw Pydantic messages in the visible UI.
- Convert the backend field path to the corresponding UI field key.
- Show the same human copy inline under that field.
- Open `More details` automatically when the invalid field lives inside that section.
- Optionally show a non-technical summary banner: `Revisa los campos marcados en rojo.`

### FR-003: Apply the rule to all form inputs

Every editable control in `EstimationWorkbench` should have a defined field-error mapping and human-readable copy for local or backend validation:

| UI key | Backend field | Notes |
| --- | --- | --- |
| `projectName` | `project_name` | Optional, max length. |
| `projectSummary` | `project_summary` | Required, 20-200 chars after trim. |
| `projectType` | `project_type` | Required enum. |
| `targetAudience` | `target_audience` | Required enum. |
| `targetAudienceOther` | `target_audience_other` | Required when target audience is `other`. |
| `projectDescription` | `project_description` | Required, min/max length. |
| `deliverablesText` | `deliverables` | One deliverable per line, 3-8 lines, per-line cap. |
| `deliveryUrgency` | `delivery_urgency` | Required enum. |
| `targetDate` | `target_date` | Required when urgency implies a fixed date. |
| `dataSensitivity` | `data_sensitivity` | Required enum. |
| `detailLevel` | `detail_level` | Required enum. |
| `outputFormat` | `output_format` | Required enum. |
| `attachments` | `attachments` | Max count/type/size errors. |
| `outOfScopeText` | `out_of_scope` | One item per line, max count and length. |
| `deliveryApproach` | `delivery_approach` | Optional enum. |
| `integrationCategories` | `integration_categories` | Multi-select, including `none` exclusivity. |
| `integrationCustomText` | `integration_custom_names` | One item per line, max 3 entries, 40 chars per line. |
| `industry` | `industry` | Optional enum. |
| `industryOther` | `industry_other` | Required when industry is `other`. |
| `hostingConstraints` | `hosting_constraints` | Multi-select. |
| `hostingNotes` | `hosting_notes` | Optional, max length. |
| `teamContext` | `team_context` | Optional enum. |
| `uiLanguages` | `ui_languages` | Max 3 selections. |
| `riskLevel` | `risk_level` | Optional enum. |
| `externalDependenciesText` | `external_dependencies` | One item per line, max count and length. |
| `preprocessing` | `preprocessing` | Optional enum/default. |
| `evaluate` | `evaluate` | No inline error expected unless backend rejects type. |

### FR-004: Accessible inline display

When a field is invalid:

- Set `aria-invalid="true"` on the control.
- Link the error or hint text with `aria-describedby`.
- Render the inline error below the field with readable contrast.
- Apply a visible error style to the control, such as red border/ring.
- Use an error label style or equivalent visual treatment where practical.
- Move focus to the first invalid field on submit.

### FR-005: No raw technical leakage

End users must not see:

- `HTTP 422`
- `Value error`
- `integration_custom_names`
- Backend field names in snake_case
- Raw backend validation messages when a field mapping exists

Unknown non-validation API failures may still use a safe global message, but should not expose raw response bodies by default.

## Technical Approach

### Error model

Create a small frontend normalization layer, for example:

```ts
type FormErrorState = {
  fieldErrors: Record<string, string>
  formError?: string
}
```

Inputs:

- Zod issues from `parseEstimationForm`.
- FastAPI 422 JSON responses with `detail`.
- Attachment conversion errors from `filesToAttachments`.
- Unknown network or server failures.

Output:

- Field-level errors keyed by UI field names when the failing field can be identified.
- A safe `_form` or `formError` summary only when no field mapping is available.

### Field mapping

Keep one explicit mapping table from backend fields to UI keys. It should handle FastAPI locations such as:

```text
["body", "integration_custom_names", 0]
["integration_custom_names"]
```

The normalizer should extract the first known backend field from the path and map it to the UI field key.

### Copy mapping

Start with explicit copy for known validations rather than trying to show raw backend text. For example:

- `integration_custom_names` length/count/empty issues -> `Cada integración debe ocupar una línea y tener como máximo 40 caracteres.`
- `deliverables` count issue -> `Añade entre 3 y 8 entregables, uno por línea.`
- Required select issues -> `Selecciona una opción.`
- Conditional `target_date` -> `Selecciona una fecha objetivo para esta urgencia.`

If a backend field is known but the exact rule is unknown, show a generic field-level message:

```text
Revisa este campo.
```

### Component props

Extend the current `Field` pattern as needed so controls can receive:

- `error`
- `errorMessage`
- `hint`
- `aria-invalid`
- `aria-describedby`

When both hint and error exist, `aria-describedby` should include both IDs.

## Acceptance Criteria

- [ ] If a custom integration line exceeds 40 characters, the `Custom integrations (optional, one per line)` field is marked invalid before submit.
- [ ] The custom integrations inline error says: `Cada integración debe ocupar una línea y tener como máximo 40 caracteres.`
- [ ] The request is not sent while local validation fails.
- [ ] If the backend returns a 422 for `integration_custom_names`, the same inline error appears under the custom integrations textarea.
- [ ] The global banner, if shown, only summarizes the issue and does not expose backend details.
- [ ] Every editable guided-form input has a field mapping and accessible invalid state.
- [ ] The first invalid field receives focus on submit; fields inside `More details` are revealed first.
- [ ] Field errors disappear after the user corrects the content.
- [ ] The UI never displays `HTTP 422`, `Value error`, or `integration_custom_names` for mapped validation errors.

## Test Plan

- Unit tests:
  - `findInvalidCustomIntegrationLines` for trimming, empty lines, and exact 40/41-character boundaries.
  - Zod validation maps custom integrations to `integrationCustomText`.
  - Backend 422 normalizer maps `integration_custom_names` to `integrationCustomText`.
  - Backend 422 normalizer maps representative fields from the full form inventory.
  - Raw technical strings are not included in mapped user-facing messages.
- Component tests, if the current setup supports them:
  - Submit with invalid custom integrations and assert inline message, `aria-invalid`, and no network call.
  - Simulate a 422 response and assert the field receives the error instead of the global technical banner.
- Manual checks:
  - Run the web app, enter a line longer than 40 characters in custom integrations, submit, and confirm inline focus/error behavior.
  - Force or mock a backend 422 for `integration_custom_names` and confirm the same UI behavior.

Suggested commands:

```bash
cd web && npm run test
cd web && npm run build
```

If backend tests are touched:

```bash
uv run pytest
```

## Documentation Plan

- Update this work item with verification evidence when implemented.
- Update `README.md` or web docs only if visible behavior or runbook instructions change.
- No `.env.example` update is expected; this feature introduces no settings or secrets.

## Baby Steps

1. Extract a field-error normalizer and tests for local + backend validation shapes.
2. Add the complete backend-field to UI-field mapping table and human copy map.
3. Wire backend 422 handling from `useEstimateStream` into `EstimationWorkbench` field errors.
4. Add hint support to `Field` and apply the custom integrations helper text.
5. Review every form input for `Field` coverage, `aria-describedby`, invalid styling, and correction clearing.
6. Run focused web tests/build and any backend tests touched.

## Verification

**Partial (this slice):** custom integration textarea enforces one line per integration and a **40-character** maximum per line (`requestMapper` + Vitest). Remaining checklist items in this document are **not** implemented yet.

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
| ---------- | ------- | --------------- |
| `c863416` | `feat(web): cap custom integration lines at 40 chars` | Per-line max length and Spanish copy for `integrationCustomText`; `findInvalidCustomIntegrationLines` helper and Vitest cases. |
