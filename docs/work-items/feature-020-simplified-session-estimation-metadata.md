# Feature: Simplified Session Estimate Contract with Derived Project Metadata

## Objective

Move session-based estimation from the current long guided-form submit to a shorter, transcript-centered request while keeping the response rich enough for the UI to show session memory, derived project metadata, and the estimate result clearly.

The backend should absorb the normalization work that the simplified form no longer carries explicitly: it must infer useful structure from sparse fields, extract text from multiple attachments, and return a first-class `project_metadata` object alongside the estimate.

## Context

- `app/routers/sessions.py` already exposes `POST /api/v1/sessions` and `POST /api/v1/sessions/{session_id}/estimate`.
- `app/services/sessions.py` already provides the in-memory session store, `Session`, `ConversationHistory`, and `ProjectMetadata`.
- The current session estimate contract is still driven by the larger guided form schema in `app/schemas/estimation_request.py`, which includes many explicit fields and inline attachment payloads.
- Related work items `feature-017`, `feature-018`, and `feature-019` established the session store, conversational metadata, and attachment/session orchestration patterns. This feature changes the public submit contract and response envelope for the session route rather than reworking the session foundation.
- The existing structured estimation path should remain behind the service layer. Routers must not call provider SDKs directly.

## Downstream

- **[`feature-021-session-based-simplified-estimator-ui.md`](feature-021-session-based-simplified-estimator-ui.md)** — frontend refactor that consumes this feature’s API contract. **Complete feature-020 before starting feature-021.**

## Scope

### Includes

- Stabilize `POST /api/v1/sessions` as the entry point for the simplified flow and return a session identifier.
- Replace the session estimate request body with a shorter payload centered on `transcript`.
- Accept multiple attachment references and resolve them server-side before estimation.
- Build and return a top-level `project_metadata` object derived from the request, transcript, and attachment content.
- Persist the latest normalized payload, derived metadata, attachment summary, and latest estimate in the session state.
- Return a structured response envelope that separates `input_payload`, `project_metadata`, `estimate`, and `warnings`.
- Keep the stateless `/api/v1/estimate` and `/api/v2/estimate` routes unchanged unless a temporary compatibility adapter is explicitly needed during rollout.

### Excludes

- Frontend changes.
- OCR, virus scanning, or a new upload pipeline.
- Database, Redis, or filesystem persistence for session state.
- Redesigning the estimation model itself.
- Changing the provider boundary or calling provider SDKs from route handlers.

## Functional Requirements

### FR-01: Session creation

- `POST /api/v1/sessions` returns `201 Created`.
- The response includes a session identifier.
- The created session starts with minimal or empty state and no prior estimate.

### FR-02: Simplified request contract

`POST /api/v1/sessions/{session_id}/estimate` accepts a simplified JSON body with these fields:

- `project_name: str` - required, trimmed, short text.
- `one_line_summary: str | null` - optional, short human summary.
- `project_type: ProjectType` - required.
- `transcript: str` - required, free-form primary narrative.
- `target_audience: TargetAudience` - required.
- `industry: Industry | null` - optional.
- `additional_extra_info: str | null` - optional, secondary context.
- `attachments: list[AttachmentRef]` - optional, multiple attachments, max 3 files, max per file 10mb. Total 30mb .

The request should be intentionally shorter than the current guided form contract. Fields that used to be explicit in the older form but are no longer part of the UI should not reappear as required inputs.

### FR-03: Transcript rules

- `transcript` is the main free-form input.
- It must be trimmed and validated.
- The backend should reject empty or too-short transcripts.
- The transcript may include discovery notes, rough requirements, assumptions, and notes from a sales or product conversation.

### FR-04: Attachment references

- The request supports multiple attachments.
- Each attachment entry includes at minimum `file_id`, `name`, and `mime_type`.
- The backend resolves each attachment by `file_id` and extracts useful text when the MIME type is supported.
- Attachment processing must be bounded and deterministic.
- Unsupported, missing, or unreadable attachments should be reported clearly without leaking secrets or raw file contents.

### FR-05: Project metadata derivation

The backend must build a first-class `project_metadata` object from the request and resolved attachments.

At minimum, the metadata should include:

- `project_name`
- `project_type`
- `target_audience`
- `industry`
- `summary`
- `derived_deliverables`
- `detected_constraints`
- `attachment_summary`
- `confidence_notes`

The derived metadata should combine:

- explicit request fields,
- normalized transcript content,
- attachment text where available,
- and lightweight inference for missing structure.

### FR-06: Missing context handling

- The backend should not fail just because the simplified form omits fields that used to be explicit.
- Instead, it should emit warnings when important context is missing or only inferred.
- At minimum, warnings should cover missing urgency, depth expectations, output shape preference, data sensitivity uncertainty, or other obvious gaps that used to be explicit in the old guided form.
- Missing context should reduce confidence notes in the metadata when applicable.

### FR-07: Estimation execution

- The estimator must run using the normalized payload plus the derived metadata and session context.
- The route should stay thin and delegate the business logic to a service layer.
- The service may use a compatibility adapter internally so the existing estimation core can keep working while the public contract changes.
- If the compatibility adapter is used, it must be isolated from the router and from the public schema.

### FR-08: Session persistence

The session state should retain at least:

- the last normalized input payload,
- the latest derived `project_metadata`,
- the latest estimate,
- attachment references and their processing status,
- creation and update timestamps.

Remind, this sessions persit on python dictionary structure by the moment. SO, persistence type is dictionary structure, volatiule memory. App restart, clean memory.

This lets the UI re-open the session and show the same memory and output without recomputing the full request shape.

### FR-09: Response shape

The estimate response should be a structured envelope with at least:

- `session_id`
- `input_payload`
- `project_metadata`
- `estimate`
- `warnings`
- `attachments` or an attachment processing summary

`project_metadata` must be a first-class top-level object, not an implicit derived side effect.

### FR-10: Error handling

- Unknown sessions return `404`.
- Invalid request data returns `422`.
- Attachment resolution failures should be specific and safe.
- Large or unsupported attachments should fail deterministically with a user-safe message.
- No raw provider errors, file contents, tokens, or secrets should leak to the client.

### FR-11: Compatibility expectations

- The new public session contract should be the default path for the simplified UI.
- Keeping a temporary internal adapter to the older guided-form estimator is acceptable during rollout.
- If a compatibility path for the old session body is needed, it must be documented as transitional and not treated as the new canonical UI contract.

## Technical Approach

1. Keep `app/routers/sessions.py` thin.
2. Add or extend a service in `app/services/` that:
   - validates the simplified request,
   - resolves attachments,
   - extracts attachment text,
   - normalizes the transcript and extra notes,
   - derives `project_metadata`,
   - executes the estimate,
   - and persists the session snapshot.
3. Reuse the current provider chain and `complete_structured`-based estimation flow through the service boundary when structured inference is needed.
4. Keep the old guided-form estimator behind an adapter if it reduces migration risk.
5. Return a response envelope that wraps the estimate result and the derived metadata for the UI.

### Request and response models

The implementation should introduce dedicated session-scoped DTOs rather than overloading the existing guided-form schema.

Suggested shape:

- `SessionEstimateRequest` for the simplified input.
- `AttachmentRef` for attachment references.
- `SessionEstimateResponse` for the new envelope.
- `ProjectMetadata` extended to represent derived UI-facing memory, not just raw session facts.

### Data flow

```text
Client
  -> POST /api/v1/sessions
  -> POST /api/v1/sessions/{session_id}/estimate
       -> routers/sessions.py
       -> session estimation service
            -> session_store.get_session(session_id)
            -> attachment resolver / text extraction
            -> request normalization
            -> project_metadata derivation
            -> estimation execution
            -> session snapshot update
       -> SessionEstimateResponse
```

### Validation defaults

- `project_name`: required.
- `one_line_summary`: optional, short if present.
- `project_type`: required.
- `transcript`: required, with a meaningful minimum and maximum length.
- `target_audience`: required.
- `industry`: optional, but if absent the response should surface a warning.
- `additional_extra_info`: optional, capped to avoid prompt bloat.
- `attachments`: optional, multiple allowed, subject to existing size and MIME constraints.

### Migration note

The current guided-form session contract already exists in the repo. This feature intentionally changes the public shape to match the simplified UI. Keep the transformation logic isolated so future refactors can replace the adapter without changing the route contract again.

## Acceptance Criteria

- [ ] AC-01: `POST /api/v1/sessions` returns `201 Created` with a session identifier.
- [ ] AC-02: The new session starts with empty or minimal state and no prior estimate.
- [ ] AC-03: `POST /api/v1/sessions/{session_id}/estimate` accepts the simplified request contract only.
- [ ] AC-04: `project_name`, `project_type`, `transcript`, and `target_audience` are validated as required inputs.
- [ ] AC-05: The backend rejects empty or too-short `transcript` values with a safe validation error.
- [ ] AC-06: The request supports multiple attachments and processes each attachment independently.
- [ ] AC-07: Attachment resolution and text extraction produce per-attachment status information.
- [ ] AC-08: The response includes a top-level `project_metadata` object.
- [ ] AC-09: `project_metadata` includes derived fields such as summary, derived deliverables, detected constraints, attachment summary, and confidence notes.
- [ ] AC-10: The response separates `input_payload`, `project_metadata`, `estimate`, and `warnings`.
- [ ] AC-11: Missing context such as urgency or sensitivity produces warnings instead of hard failure.
- [ ] AC-12: The session store persists the latest normalized payload, metadata, attachment status, and estimate.
- [ ] AC-13: Unknown session IDs return `404`.
- [ ] AC-14: Unsafe provider, file, or extraction failures do not leak secrets or raw stack traces to the client.
- [ ] AC-15: The current stateless estimation routes remain unaffected unless a temporary rollout adapter is explicitly added.

## Test Plan

- Unit tests:
  - request validation for required and optional fields,
  - transcript trimming and length checks,
  - attachment reference validation,
  - metadata derivation from sparse input,
  - warning generation for missing context,
  - session-state persistence updates.
- Integration tests:
  - `POST /api/v1/sessions`,
  - `POST /api/v1/sessions/{session_id}/estimate`,
  - `404` for unknown sessions,
  - multiple attachment handling with mocked extraction.
- Manual checks:
  - run `uv run uvicorn app.main:app --reload`,
  - create a session,
  - submit a simplified estimate payload with multiple attachments,
  - verify the response shows `project_metadata`, warnings, and the estimate envelope.

## Verification

- **Verified:** `uv run pytest` — 272 passed (schemas, adapter, router envelope, full suite).
- **Verified:** `POST /api/v1/sessions/{id}/estimate` accepts simplified body only; legacy `user_message` → `422`.
- **Not verified:** Manual smoke with real PDF/DOCX attachments and Langfuse span review.
- **Residual risk:** `file_id`-only refs without inline `content_base64` fail per-file until upload API; attachment extraction not exercised against production-sized binaries in CI.

## Documentation Plan

- Update `README.md` to document the simplified session workflow, request body, and response envelope.
- Update `docs/technical/README.md` to reflect the new session-based estimation contract and `project_metadata` semantics.
- Update the relevant Second Brain note for the session workflow and any migration gotchas.
- If attachment limits or settings change during implementation, update `.env.example` as well.

## Learnings

- Keep the router thin and the normalization logic in `app/services/`.
- Do not reintroduce the old guided form as the public session contract.
- Treat `project_metadata` as the UI-facing memory layer, not as a free-text dump.
- Preserve the in-memory session store for now; persistence is a separate problem.
- Use the existing structured LLM helper and provider chain if inference is needed; do not invent a new provider entry point in the route handler.

## Implementation Plan

- [ ] Step 1: Define the simplified session request/response models and extend session state for the new envelope.
- [ ] Step 2: Add the normalization and attachment-resolution service with unit tests.
- [ ] Step 3: Wire `POST /api/v1/sessions/{session_id}/estimate` to derive metadata, run estimation, and persist the session snapshot.
- [ ] Step 4: Add router integration tests and verify the new response contract.
- [ ] Step 5: Update README and technical docs, then run the focused and full `uv run pytest` checks.

## Estimation

- Size: M
- Estimated time: 4-6 hours
- Planned steps: 7

## Pull request

- WIP draft: https://github.com/povedica/master-ia-lidr/pull/17
- Branch: `feature/020-simplified-session-estimation-metadata`

## Implementation progress

- [x] Step 1: Simplified request/response schemas + extended `ProjectMetadata`
- [x] Step 2: Session state fields for normalized payload and attachment status
- [x] Step 3: Normalization, warnings, and guided-form adapter
- [x] Step 4: Attachment resolver (`AttachmentRef` + transitional inline base64)
- [x] Step 5: Metadata derivation service (deterministic; no extra LLM pass)
- [x] Step 6: Wire router + `SimplifiedSessionEstimationService.run_submit`
- [x] Step 7: Integration tests, README, `.env.example`, full pytest

## Repository commits (master-ia)

| Commit | Summary |
| --- | --- |
| docs | Add feature-020 canonical work item |
| feat | Simplified session estimate schemas and DerivedProjectMetadata |
| feat | Simplified session estimation pipeline, router envelope, tests |

## Definition of Done (technical)

Use this checklist at the end of `/start-task` before calling the feature complete. Every item should be checked or explicitly marked N/A with a one-line reason in the work item **Verification** section.

### API contract and routing

- [ ] **DOD-01:** `POST /api/v1/sessions` returns `201` with `{ "session_id": "<uuid>" }` and initializes empty/minimal session state.
- [ ] **DOD-02:** `POST /api/v1/sessions/{session_id}/estimate` accepts the **simplified** body only (`project_name`, `one_line_summary`, `project_type`, `transcript`, `target_audience`, `industry`, `additional_extra_info`, `attachments[]`) — not the full guided `EstimationRequest`.
- [ ] **DOD-03:** OpenAPI (`/docs`) documents the new request and response models with field descriptions and validation constraints.
- [ ] **DOD-04:** Unknown `session_id` → `404` with a safe message (no stack trace).
- [ ] **DOD-05:** Invalid payload (missing required fields, transcript too short/long, bad attachment ref) → `422` with field-level or structured detail.

### Request validation

- [ ] **DOD-06:** `project_name`, `project_type`, `transcript`, and `target_audience` are enforced as required after trim.
- [ ] **DOD-07:** `transcript` min/max length matches the spec (document exact values in code and README).
- [ ] **DOD-08:** `one_line_summary` and `additional_extra_info` respect optional caps when present.
- [ ] **DOD-09:** `industry` optional; when absent, response includes a **warning** (not a hard failure).

### Attachments

- [ ] **DOD-10:** Multiple `attachments[]` entries are accepted up to configured count/size/MIME limits.
- [ ] **DOD-11:** Each attachment is resolved by `file_id`, extracted when MIME is supported, and reported with per-file status (`processed`, `failed`, `unsupported`, etc.).
- [ ] **DOD-12:** Oversize, unsupported MIME, missing `file_id`, or extraction failure returns deterministic HTTP errors (`413` / `422` as appropriate) without leaking file bytes or secrets in logs/responses.
- [ ] **DOD-13:** Extracted attachment text is bounded before prompt/LLM use (reuse or align with existing `MAX_ATTACHMENT_*` settings).

### `project_metadata` and warnings

- [ ] **DOD-14:** Response exposes **`project_metadata` as a top-level object** (not nested only inside `estimate` or implicit fields).
- [ ] **DOD-15:** `project_metadata` includes at minimum: `project_name`, `project_type`, `target_audience`, `industry`, `summary`, `derived_deliverables`, `detected_constraints`, `attachment_summary`, `confidence_notes`.
- [ ] **DOD-16:** Metadata is derived from explicit request fields + normalized transcript + attachment text + inference; behavior is covered by unit tests with mocked LLM where applicable.
- [ ] **DOD-17:** Response includes **`warnings`** when former guided-form fields are missing (e.g. urgency, depth, output format, data sensitivity) instead of failing the request.
- [ ] **DOD-18:** `confidence_notes` reflect inferred vs explicit context (e.g. “urgency not explicitly provided”).

### Response envelope and estimation

- [ ] **DOD-19:** Successful response separates **`session_id`**, **`input_payload`** (normalized submit), **`project_metadata`**, **`estimate`** (structured result), and **`warnings`**.
- [ ] **DOD-20:** `estimate` shape remains compatible with UI expectations (structured totals/phases/assumptions/risks or documented mapping from `EstimationResponse`).
- [ ] **DOD-21:** Estimation runs through **service layer** (`SessionEstimationService` or successor); router does not call OpenAI/Anthropic/LiteLLM directly.
- [ ] **DOD-22:** If a guided-form **adapter** is used internally, it lives in `app/services/` and is covered by tests; it is not the public session contract.

### Session persistence (in-memory)

- [ ] **DOD-23:** After a successful submit, session stores: last normalized payload, latest `project_metadata`, latest estimate, attachment refs + processing status, `updated_at` (and `submit_count` if retained).
- [ ] **DOD-24:** `GET /api/v1/sessions` (if unchanged) still lists sessions; summaries remain consistent with new submit shape (e.g. `project_name` from latest payload/metadata).
- [ ] **DOD-25:** A second submit on the same `session_id` replaces/updates the snapshot and increments activity counters as designed.

### Architecture, safety, and compatibility

- [ ] **DOD-26:** Stateless `POST /api/v1/estimate` and `POST /api/v2/estimate` behavior unchanged unless an explicit transitional adapter is documented in README.
- [ ] **DOD-27:** No API keys, tokens, full transcripts, or raw attachment bodies in logs, tests, or committed docs.
- [ ] **DOD-28:** Langfuse (if enabled) traces session estimate with **store `session_id`** and spans for load / attachment / normalize / estimate (align with feature-019 pattern).
- [ ] **DOD-29:** Guardrail and pipeline error shapes match existing estimation routes (`422` / `503` with `code`, safe `message`, `audit_id` where applicable).

### Tests

- [ ] **DOD-30:** Unit tests: validation, normalization, metadata derivation, warnings, attachment status aggregation (mocked extraction/LLM).
- [ ] **DOD-31:** Integration tests: create session → estimate → assert envelope; 404 unknown session; multi-attachment path with mocks.
- [ ] **DOD-32:** `uv run pytest` full suite green; `uv run pytest --collect-only` zero import/collection errors.
- [ ] **DOD-33:** No test requires a real API key for default CI/local run.

### Documentation and configuration

- [ ] **DOD-34:** `README.md` documents simplified session workflow, example JSON request/response, and breaking change vs guided session body (feature-019).
- [ ] **DOD-35:** `docs/technical/README.md` updated for contract, metadata semantics, and attachment resolution model.
- [ ] **DOD-36:** If new env vars or limits are introduced, `.env.example` and README list them (no real secrets).
- [ ] **DOD-37:** **Verification** section in this work item states **Verified** / **Not verified** / **Residual risk** per repo done-gates.

### Manual smoke (recommended before merge)

- [ ] **DOD-38:** `uv run uvicorn app.main:app --reload` starts without import errors.
- [ ] **DOD-39:** `curl` flow: create session → submit simplified payload with `transcript` + 2 attachment refs → response shows `project_metadata`, `warnings`, and `estimate`.
- [ ] **DOD-40:** UI or API client “new conversation” = new `POST /sessions`; prior `session_id` state is not required for the new submit.

### Completion record

- [ ] **DOD-41:** All **Acceptance Criteria (AC-01–AC-15)** checked or explicitly deferred with follow-up noted in this file.
- [ ] **DOD-42:** `## Repository commits (master-ia)` table added/updated during `/finish-task` with implementation commits.
