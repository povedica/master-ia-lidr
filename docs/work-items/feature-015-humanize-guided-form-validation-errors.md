# Feature: Humanized guided form validation errors

## Objective

Turn technical validation failures in the guided estimation form into clear, inline, accessible field errors. The immediate user-facing problem is the backend 422 message for custom integrations:

```text
HTTP 422: Value error, each integration_custom_names entry must be at most 40 characters
```

That text must never be shown to end users. The form should instead mark the affected field and show human copy such as:

```text
Each integration must be on its own line and at most 40 characters per line.
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
  - `One integration per line. Up to 40 characters per line.`
- Preserve or improve current scroll/focus behavior for the first invalid field, including fields inside the `More details` disclosure.
- Keep global banners as summaries only, for example:
  - `Please review the fields highlighted in red.`
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
- Mark the field invalid when any non-empty line has fewer than 20 or more than 300 characters.
- Prevent submit while invalid.
- Focus and scroll to the textarea.
- Clear the field error after the content is corrected.

Primary error message:

```text
Each non-empty line must be between 20 and 300 characters.
```

Optional line-specific messages:

```text
Line 1 is longer than 300 characters.
Lines 1 and 2 are shorter than 20 characters.
```

### FR-002: Backend 422 field normalization

When the API returns HTTP 422 and the response contains validation details for a known request field:

- Do not show `HTTP 422`, `Value error`, raw backend field names, or raw Pydantic messages in the visible UI.
- Convert the backend field path to the corresponding UI field key.
- Show the same human copy inline under that field.
- Open `More details` automatically when the invalid field lives inside that section.
- Optionally show a non-technical summary banner: `Please review the fields highlighted in red.`

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
| `integrationCustomText` | `integration_custom_names` | One item per line, max 3 entries, 20–300 chars per line. |
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

- `integration_custom_names` length/count/empty issues -> `Each non-empty line must be between 20 and 300 characters.`
- `deliverables` count issue -> `Add between 3 and 8 deliverables, one per line.`
- Required select issues -> `Required.`
- Conditional `target_date` -> `Please pick a target date for this urgency level.`

If a backend field is known but the exact rule is unknown, show a generic field-level message:

```text
Please review this field.
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

- [x] If a custom integration line exceeds 40 characters, the `Custom integrations (optional, one per line)` field is marked invalid before submit.
- [x] The custom integrations inline error uses the English primary sentence: `Each integration must be on its own line and at most 40 characters per line.` (optionally followed by per-line hints from Zod).
- [x] The request is not sent while local validation fails.
- [x] If the backend returns a 422 for `integration_custom_names`, the same inline error appears under the custom integrations textarea (via `parseStructuredEstimateFailure`).
- [x] The global banner, if shown, only summarizes the issue and does not expose backend details.
- [x] Every editable guided-form input has a field mapping and accessible invalid state (backend map + existing `Field` wiring; local Zod humanized for common paths).
- [x] The first invalid field receives focus on submit; fields inside `More details` are revealed first (existing behavior preserved).
- [x] Field errors for custom integrations persist while typing until every non-empty line is 20–300 characters (re-validated on each form state change, not cleared on first keystroke).
- [x] The UI never displays `HTTP 422`, `Value error`, or `integration_custom_names` for mapped validation errors (normalized paths).

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

## Implementation progress

- [x] Step 1: Field-error normalizer module (`validationErrors.ts`) + Vitest for 422 + Zod humanization.
- [x] Step 2: Backend-field → UI-key map + English copy for mapped validations.
- [x] Step 3: `useEstimateStream` returns validation outcome; `EstimationWorkbench` applies field errors + summary banner.
- [x] Step 4: `Field` supports `hint` + combined `aria-describedby`; custom integrations persistent hint.
- [x] Step 5: Inventory keys covered in `BACKEND_FIELD_TO_UI`; guided controls use `Field` (unchanged layout).
- [x] Step 6: `cd web && npm run test -- --run src/features/estimation` and `npm run build`.

## Verification

**Verified (automated):**

- `cd web && npm run test -- --run src/features/estimation` — all estimation Vitest files pass (includes `validationErrors.test.ts`, `requestMapper.test.ts`, `sseParser.test.ts`).
- `cd web && npm run build` — TypeScript project build and Vite production build succeed.

**Verified (code review / partial):**

- 422 responses with mappable `detail` entries populate `fieldErrors` with English copy and set the hook `error` state to `null`, so the red global banner does not show raw `HTTP 422` / `Value error` for those cases.
- Local `ZodError` paths use `humanizeZodIssuesToFieldErrors`; required selects show `Required.`; custom integrations enforce 20–300 chars per non-empty line with sticky errors until valid.

**Not verified:**

- Full manual browser pass (custom integrations submit, forced backend 422).
- Component tests (Vitest + RTL) for submit without network — not added in this slice.

**Residual risk:**

- Rare Pydantic / FastAPI `loc` shapes that omit every mapped segment may still fall back to the generic 422 banner without field mapping.
- `filesToAttachments` errors may still surface English technical text in the `attachments` field until that path is humanized separately.

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
| ---------- | ------- | --------------- |
| `c863416` | `feat(web): cap custom integration lines at 40 chars` | Earlier slice: per-line max 40 and Vitest helper (superseded by 20–300 in later commits). |
| `4db286f` | `feat(web): add validationErrors normalizer for 422 and Zod` | `validationErrors.ts` + tests; backend field map and English copy for 422 detail. |
| `0b5ba30` | `feat(web): humanize guided form validation UX` | Workbench, `useEstimateStream`, `requestMapper`; required `*` labels, sticky re-validation, 20–300 custom lines. |
| `9b6531b` | `feat(api): enforce custom integration line length 20-300` | `EstimationRequest` min/max per line; Python regression tests. |
| `1b405b5` | `docs(feature-015): record humanized validation UX and verification` | Work item acceptance, limits, verification evidence, commit log. |
