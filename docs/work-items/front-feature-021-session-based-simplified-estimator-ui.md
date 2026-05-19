# Feature: Session-Based Simplified Estimator UI

## Objective

Refactor the existing React estimator UI (`web/`) into a **session-first, simplified guided form** with three clearly separated zones: **user input**, **derived memory** (`project_metadata`), and **system output** (estimate result).

The screen must feel like an evolution of the current Estimator (professional SaaS, high legibility, clean spacing), not a new product and **not** a chat UI.

## Depends on

**Blocking dependency:** [`feature-020-simplified-session-estimation-metadata.md`](feature-020-simplified-session-estimation-metadata.md)

Do **not** start `/start-front-task` on this work item until feature-020 is **done** (or explicitly marked complete in its work item with verification recorded). This UI feature assumes the backend already provides:

| Capability | Owner |
| --- | --- |
| Simplified `POST /api/v1/sessions/{session_id}/estimate` request body (`project_name`, `one_line_summary`, `project_type`, `transcript`, `target_audience`, `industry`, `additional_extra_info`, `attachments`) | feature-020 |
| Response envelope with top-level `project_metadata`, `estimate`, `warnings`, `input_payload`, `session_id` | feature-020 |
| `POST /api/v1/sessions` unchanged (`201` + `session_id`) | feature-020 (stabilize) |
| Attachment rules and validation aligned with OpenAPI | feature-020 |

**Rollout order:** implement and verify **feature-020 first**, then **front-feature-021**.

If feature-020 is only partially shipped, stop and finish feature-020 — do not mock the envelope long-term or keep calling `POST /api/v2/estimate` as a workaround in the primary UI path.

### Related (non-blocking)

| Work item | Role |
| --- | --- |
| [`feature-019-file-attachment-dynamic-context.md`](feature-019-file-attachment-dynamic-context.md) | Session store and attachment extraction foundation |
| [`feature-010-remove-streamlit-split-backend-web.md`](feature-010-remove-streamlit-split-backend-web.md) | `web/` stack (React, Vite, Tailwind, Zod) |

## Context

### Current UI (`web/`)

| Area | Location | Today |
| --- | --- | --- |
| Shell | `web/src/App.tsx` | Single column, `max-w-3xl`, theme control only in top bar |
| Main screen | `web/src/features/estimation/components/EstimationWorkbench.tsx` | Long guided form (~20+ fields), collapsible “more details”, violet primary actions |
| Submit | `web/src/features/estimation/hooks/useEstimateStream.ts` | `POST /api/v2/estimate` (stateless structured JSON) |
| Request mapping | `web/src/features/estimation/lib/requestMapper.ts` | Maps full `EstimationFormValues` → legacy guided payload |
| Attachments | `web/src/features/estimation/lib/fileToBase64.ts` | Up to 3 files, base64 inline, 256 KiB cap |
| Result | `StructuredEstimateSummary` inside `EstimationWorkbench.tsx` | Rendered **below the form** in the same column; no metadata panel |
| Branding | Header copy | “Estimador CAG”, documents v2 endpoint in subtitle |

There is **no session integration** in the web app today (`grep` shows no `session_id` usage under `web/`).

The submit and response shapes below are defined by **feature-020**; this document describes how the UI consumes them.

### API surface (canonical for this UI)

All paths are relative to `VITE_API_BASE_URL` (default `http://127.0.0.1:8000`).

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/sessions` | Create session on load / “New conversation” → `{ "session_id": "<id>" }`, `201` |
| `POST` | `/api/v1/sessions/{session_id}/estimate` | Submit simplified form → envelope with `project_metadata` + `estimate` |

Do **not** call `POST /api/v2/estimate` from the refactored primary flow.

### Design references (product)

Attach during implementation for visual alignment:

| Asset | Intent |
| --- | --- |
| `assets/image-d5e36a8d-3a3e-42f0-88e6-5ae4afb44acc.png` | Target layout: header + 2-column main + full-width result; teal accent; metadata as structured JSON panel |
| `assets/image-55f0e60d-9feb-4f3c-a407-1f3755a10ea8.png` | Before/after narrative: shorter form, visible memory, separated output (not chat bubbles) |

## Product Goal

Reduce cognitive load while making **session**, **memory**, and **output** obvious so users understand:

1. what they are typing (input),
2. what the system inferred (metadata),
3. what the estimator produced (result).

## Users and Use Cases

- **Primary user:** Consultant / engineer preparing a project estimate from notes or a transcript.
- **Secondary user:** Reviewer validating derived metadata vs. raw input.
- **Core scenario:** Open app → session auto-created → fill short form → generate estimate → read metadata + result on one screen.
- **Adjacent scenario:** Start a new conversation (new session) without stale form/metadata/result from the previous run.

## Scope

### Includes

- Refactor `EstimationWorkbench` (or successor) layout: header, 2-column main, full-width result panel.
- Auto `POST /api/v1/sessions` on page load; show `session_id` in header.
- **Nueva conversación** / **New conversation** button: new session + full UI reset.
- Simplified form with **only** the nine fields listed below, exact order.
- Submit to `POST /api/v1/sessions/{session_id}/estimate` with snake_case payload keys.
- Visible **Project metadata** panel (right on desktop).
- Separate **Estimate result** panel (full width below main).
- Explicit UI states (initializing, loading, empty, success, error).
- Client validation aligned with simplified contract (drop legacy field rules).
- Reuse existing primitives: `Field`, Tailwind patterns, `StructuredEstimateSummary` (extend, don’t rewrite from scratch).
- Remove dead code: old form fields, `moreDetailsOpen`, guided mapper paths, v2-only hook usage for primary submit.
- Keep theme control (`ThemeControl`) in header area.

### Excludes

- Left sidebar **session history list** (as in mockup) — out of scope unless added in a follow-up.
- Chat bubbles, message timeline, or conversational turn UI.
- Landing-page marketing sections, hero imagery, gradient “AI app” aesthetics (purple blobs, glassmorphism, orbs).
- Any backend work (owned entirely by **feature-020**).
- Auth, multi-user accounts, persistent session store across server restarts.
- `GET /api/v1/sessions` UI (list endpoint may exist; no list UI in this feature).
- OCR, new upload microservice, or attachment storage redesign.
- Replacing Tailwind or introducing a component library.

## UX Principles

- **Interaction model:** Single-page guided estimator; one primary action (`Generate estimate`).
- **Information hierarchy:** Input (left) → Memory (right) → Output (bottom); never mix estimate into the form card.
- **Feedback strategy:** Inline field errors; panel-level loading skeletons; global alert only for session bootstrap failure.
- **Error recovery:** Retry session create; fix validation and resubmit; new conversation clears bad state.
- **Trust and clarity:** Show `session_id` verbatim (truncated visually on small screens with `title` tooltip for full value); metadata labeled as derived/auto-generated.

## User Flow

1. User opens `/` → UI shows **Initializing session** (header + disabled form).
2. `POST /api/v1/sessions` succeeds → **Session ready**; `session_id` visible; form enabled.
3. User fills fields (optional fields clearly optional).
4. User clicks **Generate estimate** → submit disabled, metadata panel may show loading, result panel shows loading.
5. Success → metadata populated from `project_metadata`; result panel shows structured estimate; form remains editable for another submit on same session (same `session_id`) unless product decides to lock — **default: allow re-submit on same session** (backend replaces snapshot).
6. User clicks **New conversation** → new session created; all panels reset to empty; form cleared.
7. On session create failure → blocking error with retry; form stays disabled.
8. On estimate failure → result panel error; metadata unchanged or partial per response; form re-enabled.

## Layout and Information Architecture

### Desktop (≥ `lg`, 1024px)

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ Estimator          session_id: sess_…     [New conversation]  [theme]       │
├──────────────────────────────┬──────────────────────────────────────────────┤
│ Project information (card)   │ Project metadata (card / panel)              │
│  - simplified form           │  - empty | loading | JSON/grouped KV         │
│                              │  - footer: "Auto-generated from inputs"      │
├──────────────────────────────┴──────────────────────────────────────────────┤
│ Estimate result (full width card)                                           │
│  - empty | loading | success (summary + breakdown) | error                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

- App max width: increase from `max-w-3xl` to ~`max-w-6xl` or `max-w-7xl` centered.
- Main grid: `grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(320px,400px)]` (tune in implementation).
- Vertical rhythm: `gap-6` between regions; cards use existing border/bg tokens.

### Mobile / tablet (`< lg`)

Stack order:

1. Header (sticky optional)
2. Form
3. Project metadata (collapsible **optional** enhancement — if not collapsible, stack as full-width section)
4. Estimate result

No horizontal scroll on textareas; file list wraps.

## UI/Interaction Requirements

### Header

| Element | Behavior |
| --- | --- |
| Title | `Estimator` (replace “Estimador CAG”) |
| `session_id` | Monospace chip or inline code; copy-to-clipboard button optional but recommended |
| Status pill | `Active` when session ready; `Initializing…` / `Error` otherwise |
| **New conversation** | Primary outline or secondary button; calls `POST /api/v1/sessions`, swaps id, resets all state |
| Theme | Keep `ThemeControl` at header right |

During **New conversation in progress**: disable button + show spinner label `Starting…`.

### Simplified form (left column)

**Section title:** `Project information`  
**Subtitle (one line):** `Provide essential project details for the estimator.`

Fields in **exact order** (do not reorder):

| # | Label | Control | Required | API key | Notes |
| --- | --- | --- | --- | --- | --- |
| 1 | Project name | `input` text | Yes | `project_name` | `maxLength` per backend |
| 2 | One-line summary | `input` text | No | `one_line_summary` | Short helper: optional elevator pitch |
| 3 | Project type | `select` | Yes | `project_type` | Reuse enum options from current `PROJECT_TYPES` (humanized labels in UI) |
| 4 | Transcript | `textarea` | Yes | `transcript` | **Largest visual weight** (`min-h` ≥ 200px desktop); helper: main description or meeting transcript |
| 5 | Target audience | `select` | Yes | `target_audience` | Reuse `TARGET_AUDIENCES`; keep `other` + conditional text field if backend still requires free text |
| 6 | Industry | `select` | No | `industry` | Reuse `INDUSTRIES`; optional |
| 7 | Attachments | `input type=file" multiple` | No | `attachments` | See attachment rules below |
| 8 | Additional extra info | `textarea` | No | `additional_extra_info` | **Lower visual weight** (`min-h` ~ 80–100px); helper: optional complementary notes |
| 9 | — | Button | — | — | **Generate estimate** (`type="submit"`) |

**Removed fields (must not appear in DOM or validation):**  
`deliverables`, `delivery urgency`, `target date`, `delivery approach`, `out of scope`, `integrations`, `data sensitivity`, `hosting`, `team context`, `UI languages`, `risk`, `external dependencies`, `depth of estimate`, `output format`, `preprocessing`, `evaluate`, `industryOther` unless required by enum `other`, and any “more details” accordion.

**Submit rules:**

- Block submit if `session_id` is null/undefined.
- Disable submit while `estimateStatus === 'loading'`.
- Remove **Cancel request** unless streaming is reintroduced (not in scope).
- On `422`, map field errors to simplified keys (`project_name`, `transcript`, …).

### Project metadata panel (right column)

| Requirement | Detail |
| --- | --- |
| Title | `Project metadata` |
| Purpose copy | One line: derived memory for debugging and transparency |
| Presentation | Prefer grouped sections (General, Context, Requirements) **or** pretty-printed JSON in a dark code block (mockup style); must be scannable |
| Tabs | Optional `Readable` / `Memory` — **not required** for MVP; single view is enough if grouped well |
| Footer | `Auto-generated from inputs` + relative timestamp when available |
| Update trigger | After successful estimate response; optionally show stale metadata from previous submit until new response arrives |

**Panel states:**

| State | UI |
| --- | --- |
| Empty | Placeholder: “Metadata will appear after you generate an estimate.” |
| Loading | Skeleton or spinner overlay during submit |
| Available | Render `project_metadata` object |
| Error | Only if a dedicated metadata fetch fails (not expected in MVP); otherwise rely on submit error |

### Estimate result panel (full width below)

| Requirement | Detail |
| --- | --- |
| Title | `Estimate result` |
| Separation | Own card; never inside form or metadata panels |

**Panel states:**

| State | UI |
| --- | --- |
| Empty | “Run Generate estimate to see the output here.” |
| Loading | Skeleton + message “Generating estimate…” |
| Success | Reuse/extend `StructuredEstimateSummary` with sections when data exists: **Summary**, **Effort breakdown** (reuse work table / metrics), **Assumptions**, **Risks**, **Next steps** — map from `estimate` object keys; show em dash when section missing |
| Error | Alert with safe message; optional `audit_id` if present in error JSON |

Do not render raw markdown stream in the primary path unless backend returns only markdown (structured `estimate` is preferred per feature-020).

## Visual Direction

- **Evolution, not revolution:** Keep slate neutrals + white/dark cards from current `EstimationWorkbench`.
- **Accent:** Shift primary CTA/focus rings from **violet** to **teal** (`teal-600` / `teal-700` hover) to align with mockup and avoid generic “AI purple” look.
- **Density:** Form card slightly more compact than today; more whitespace around result metrics.
- **Metadata panel:** Dark inset (`slate-900` / `slate-950`) with light monospace text for JSON mode; or light card with definition lists for readable mode.
- **Typography:** Existing scale (`text-sm` labels, `text-2xl` header title).
- **Icons:** Optional lucide-style SVGs only if already in project; do not add icon pack dependency for this feature alone.

## Responsive Behavior

| Breakpoint | Layout |
| --- | --- |
| `≥ lg` | Two columns + bottom result |
| `< lg` | Single column stack: form → metadata → result |
| Textareas | `w-full`, no fixed px width |
| File input | List selected files with name + size; wrap on narrow screens |
| Header `session_id` | Truncate with ellipsis; full id on `title` / copy |

## Accessibility Requirements

- All inputs have associated `<label>` via existing `Field` component (`htmlFor` / `id`).
- `aria-required` on required fields; `aria-invalid` + `aria-describedby` when errors present.
- `role="alert"` for form-level and panel-level errors (reuse current pattern).
- Keyboard: logical tab order top-to-bottom, left-to-right on desktop.
- Focus visible on buttons/inputs (teal ring, 2px).
- Metadata JSON block: `aria-label="Project metadata"`; if purely decorative pre, ensure screen readers get a text alternative (grouped DL preferred for a11y).
- Loading: `aria-busy="true"` on submitting form or result panel.
- Color contrast: teal buttons white text; error reds unchanged.

## Content and Copy

Use **English** UI copy (repo convention). Suggested strings:

| Key | Copy |
| --- | --- |
| Header title | `Estimator` |
| New conversation | `New conversation` |
| Submit | `Generate estimate` |
| Submit loading | `Generating…` |
| Transcript helper | `Paste the main project description, discovery notes, or meeting transcript.` |
| Additional info helper | `Optional. Constraints, links, or context that does not belong in the transcript.` |
| Metadata empty | `Metadata will appear after you generate an estimate.` |
| Result empty | `Run Generate estimate to see the output here.` |
| Session error | `Could not start a session. Check that the API is running and try again.` |

Avoid verbose tooltips and marketing language.

## States

Explicit state machine for implementation and tests:

| ID | State | Visible signals |
| --- | --- | --- |
| S1 | Initializing session | Header loading; form disabled |
| S2 | Session ready | `session_id` shown; form enabled |
| S3 | Session create error | Header error + retry |
| S4 | Form editable | Default idle |
| S5 | Submit in progress | Submit disabled; result loading; metadata loading |
| S6 | Result available | Result panel success |
| S7 | Submit error | Result panel error; form enabled |
| S8 | New conversation in progress | Header button loading; form disabled |
| S9 | Metadata empty | Right panel placeholder |
| S10 | Metadata available | Right panel populated |

## Data and API Dependencies

### Session create

```http
POST /api/v1/sessions
→ 201 { "session_id": "sess_…" }
```

### Estimate submit (contract from feature-020)

```json
{
  "project_name": "NeoBank Mobile",
  "one_line_summary": "A next-gen digital banking experience",
  "project_type": "mobile_app",
  "transcript": "…",
  "target_audience": "b2c_consumers",
  "industry": "fintech",
  "attachments": [],
  "additional_extra_info": null
}
```

### Response envelope (consume)

| Field | UI use |
| --- | --- |
| `session_id` | Confirm matches header |
| `project_metadata` | Right panel |
| `estimate` | Bottom panel (`StructuredEstimateSummary`) |
| `warnings` | Optional callout above result or below metadata |
| `input_payload` | Debug only (collapsed JSON optional) |

### Attachments (open decision)

Attachment shape is **defined by feature-020** OpenAPI (`AttachmentRef` with `file_id` and/or transitional inline payload). Current web code uses **base64 inline** against the legacy contract — replace during front-feature-021 to match whatever feature-020 documents; do not invent a third shape.

### Environment

- `VITE_API_BASE_URL` — unchanged (`.env.example` already documents).

## Technical Approach

### File-level plan

| Action | Path |
| --- | --- |
| Add API helpers | `web/src/features/estimation/api/sessionApi.ts` — `createSession()`, `estimateInSession(sessionId, body)` |
| Replace hook | `useEstimateStream.ts` → `useSessionEstimate.ts` (or refactor in place): session lifecycle + submit + metadata/result state |
| Slim mapper | `requestMapper.ts` — new `SimplifiedEstimationFormValues` + Zod schema + `mapToSessionEstimateBody()` |
| Split UI | Extract from `EstimationWorkbench.tsx`: `EstimatorHeader.tsx`, `SimplifiedEstimationForm.tsx`, `ProjectMetadataPanel.tsx`, `EstimateResultPanel.tsx`; keep thin orchestrator |
| Tests | `requestMapper.test.ts` — update for simplified fields; add hook/API unit tests with `fetch` mock |
| App shell | `App.tsx` — widen layout wrapper if needed |

### State ownership (suggested)

```text
useSessionEstimate()
  sessionId, sessionStatus ('idle'|'loading'|'ready'|'error')
  formValues, setFormField
  fileList, setFileList
  projectMetadata, metadataStatus
  estimate, estimateStatus, estimateError
  warnings
  createSession(), resetConversation(), submitEstimate()
```

`EstimationWorkbench` composes hooks + presentational children only.

### Validation (client)

New Zod schema mirrors backend required fields:

- `project_name`: non-empty trim
- `project_type`, `target_audience`: non-empty
- `transcript`: min length aligned with backend (document exact number from OpenAPI during implementation)
- `one_line_summary`, `industry`, `additional_extra_info`: optional
- `attachments`: max count/size per backend

Remove `estimationFormSchema` fields for deleted inputs.

### Error handling

| HTTP | UX |
| --- | --- |
| `422` | Field map + optional form summary |
| `404` | Session expired — prompt **New conversation** |
| `413` / attachment errors | Field `attachments` message |
| `503` | Safe generic message in result panel |
| Network | Same as today |

Never display raw stack traces or API keys.

## Design and Implementation Notes

- Reuse `StructuredEstimateSummary` for core metrics/table; add subsection renderers for assumptions/risks/next steps if present on `estimate`.
- Remove `ReactMarkdown` path from primary flow if unused after refactor (keep dependency only if still needed).
- Delete `moreDetailsOpen`, `FORM_FIELD_ORDER` entries for removed fields, `DETAILS_FIELD_KEYS`.
- Primary button classes: replace `bg-violet-600` with `bg-teal-600` (and dark mode equivalents).
- Optional: character counter on `transcript` if backend publishes max length (mockup shows `342 / 20000`).
- `GET /api/v1/sessions` not used in UI for this feature.

## Acceptance Criteria

- [x] **AC-00:** **feature-020** is complete and verified before this feature is marked done (simplified session estimate contract live in OpenAPI and manual smoke per feature-020).
- [x] **AC-01:** On page load, UI calls `POST /api/v1/sessions` and displays returned `session_id` in the header.
- [x] **AC-02:** Form contains **only** the nine defined fields in the specified order; no legacy fields remain in UI or client validation.
- [x] **AC-03:** `Transcript` is the dominant textarea; `Additional extra info` is visually secondary.
- [x] **AC-04:** File input accepts **multiple** files; selected files are listed and cleared on new conversation.
- [x] **AC-05:** Submit calls `POST /api/v1/sessions/{session_id}/estimate` with snake_case payload keys listed in this spec.
- [x] **AC-06:** Submit is blocked without `session_id` and disabled while request is in flight.
- [x] **AC-07:** **New conversation** creates a new session and resets form, files, metadata, result, and errors.
- [x] **AC-08:** **Project metadata** panel is visible on desktop (right column) and shows empty/loading/populated states.
- [x] **AC-09:** **Estimate result** panel is full width below main content and never nested inside the form.
- [x] **AC-10:** Result panel supports empty, loading, success, and error states.
- [x] **AC-11:** Success state shows scannable estimate content (summary + effort breakdown at minimum).
- [x] **AC-12:** Responsive stack on mobile/tablet without horizontal overflow on inputs.
- [x] **AC-13:** No chat bubbles or conversational timeline UI.
- [x] **AC-14:** Primary flow does not call `/api/v2/estimate`.
- [ ] **AC-15:** Screen is perceived as simpler than the pre-refactor guided form (qualitative review against before screenshot).

## Test Plan

- **Unit tests:**
  - `mapToSessionEstimateBody` maps all fields and omits removed ones.
  - Zod schema rejects empty `project_name` / `transcript` / required selects.
  - Session reset clears state (hook test with mocked `fetch`).
- **Component tests (optional but valuable):**
  - Header shows `session_id` after mocked create.
  - Submit disabled when `sessionId` null.
- **Contract tests:**
  - Mock `POST /api/v1/sessions` + `POST .../estimate` with feature-020 envelope; assert metadata + estimate panels update.
- **Manual checks:**
  - `uv run uvicorn app.main:app --reload` + `cd web && npm run dev`
  - Load page → session appears → fill form → generate → metadata + result populate
  - New conversation → clean slate
  - Resize to mobile width → column order correct
  - Dark/light theme still works

## Verification

- **Verified:** `cd web && npm run test` — 20 passed (sessionApi, simplifiedForm, validationErrors, theme).
- **Verified:** `cd web && npm run build` and `npm run lint` — clean.
- **Verified:** No primary-flow reference to `POST /api/v2/estimate` under `web/src`.
- **Not verified:** Manual E2E with live API + OpenAI key (requires local `.env` and `uv run uvicorn`).
- **Not verified:** Re-submit on same session against live backend.
- **Residual risk:** Attachment limits still align with backend 256 KiB per file (not 10 MiB doc drift); mockup assets not in repo.

## Documentation Plan

- Update `web/README.md` with session-first flow and env var.
- Update root `README.md` “Web UI” section: primary endpoint is session estimate, not v2.
- Cross-link feature-020 in technical docs when backend is done.
- Second Brain: short session note on UI zones (input / memory / output) if user maintains learning notes.

## Design Notes

- Mockup uses teal primary and dark metadata editor — adopt teal CTA; metadata panel dark theme is recommended for contrast with the light form card.
- Before/after diagram emphasizes **visible memory** and **separated output**; do not implement sidebar history in this iteration.
- Industry beside project type in mockup is a **layout optimization**; this spec keeps **strict field order** from product request (industry after target audience). Implementation may use a two-column row only where it does not violate order (e.g. do not put industry before transcript).

## Open Questions

| # | Question | Default if unresolved |
| --- | --- | --- |
| OQ-01 | Attachment transport: `file_id` vs inline base64? | **Resolve from feature-020 OpenAPI** — not in this feature’s scope to define |
| OQ-02 | Allow multiple estimates per session without new conversation? | Yes — same `session_id`, panels update on each success |
| OQ-03 | Show `warnings` array in UI? | Yes — compact list under metadata or above result |
| OQ-04 | Copy `session_id` button? | Yes — low effort, high utility |
| OQ-05 | Metadata readable vs JSON tabs? | Single grouped view for MVP |

## Learnings

- Do not bolt session behavior onto `useEstimateStream` without renaming — semantics change from stateless v2 to session envelope.
- Keep orchestration in a hook; keep `EstimationWorkbench` thin.
- Align attachment limits with backend before copying 256 KiB from legacy web code.
- **Do not start** until feature-020 is verified; integration tests against a mocked v2 or legacy guided body are out of scope.

## Implementation Plan

- [ ] **Step 0 (gate):** Confirm feature-020 is done — OpenAPI shows simplified session estimate request/response; run feature-020 smoke (`POST /sessions` → `POST .../estimate` with `transcript` + `project_metadata` in response).
- [ ] Step 1: Add `sessionApi.ts` + `useSessionEstimate` with session bootstrap and reset.
- [ ] Step 2: Introduce simplified form types, Zod schema, and mapper; remove legacy fields from tests.
- [ ] Step 3: Extract header, form, metadata, and result panels; rewire layout in `EstimationWorkbench`.
- [ ] Step 4: Connect submit to session estimate endpoint; wire metadata + result from response envelope.
- [ ] Step 5: Visual pass (teal accent, panel states, responsive stack).
- [ ] Step 6: Remove dead code (v2 URL in header, cancel stream, unused fields).
- [ ] Step 7: Tests + manual verification; update `web/README.md`.

## Estimation

- Size: M
- Estimated time: 6–8 hours
- Planned steps: 7 (Step 0 gate satisfied on 2026-05-19)

## Pull Request

- WIP draft PR: https://github.com/povedica/master-ia-lidr/pull/18

## Implementation progress

- [x] Step 0: feature-020 gate verified (OpenAPI + `## Verification` in feature-020; smoke on main)
- [x] Step 1: Session API + `useSessionEstimate` bootstrap/reset
- [x] Step 2: Simplified Zod schema + `mapToSessionEstimateBody` + attachment ref shape
- [x] Step 3: Extract header, form, metadata, result panels; widen `App.tsx` layout
- [x] Step 4: Wire submit to session estimate envelope
- [x] Step 5: Visual polish (teal CTA, panel states, responsive stack)
- [x] Step 6: Remove v2 stream path and legacy form fields
- [x] Step 7: Tests + `web/README.md` + verification record
