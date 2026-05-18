# Feature: Session-Scoped Guided Form Estimation (Attachments, History, Langfuse)

## Objective

Evolve the in-memory **session** model (feature-018) so the **guided estimation form** (`EstimationRequest`) is the primary input—not free-text chat. The client:

1. Creates a session (`POST /api/v1/sessions`).
2. Submits the **full guided form** one or more times against `POST /api/v1/sessions/{session_id}/estimate`, carrying the same `session_id`.
3. Relies on the **session orchestration service** to manage **conversation history** (sliding window), **project memory** (latest form snapshot), **attachment text extraction**, and **prompt composition** on every submit.

Also add **`GET /api/v1/sessions`** to list all in-memory sessions, and emit **Langfuse telemetry** for every session create, list, and estimate call—using the **store `session_id`** as the Langfuse session id (not an ad-hoc per-request id).

File attachments are extracted **server-side** to plain text and injected into the **user prompt** as bounded, delimited external context—never into system instructions and never as raw bytes to the LLM.

## Context

### Direction change (2026-05-19)

Earlier drafts of this work item assumed **free-text conversational** turns (`SessionEstimateRequest` with `user_message` only). That is **obsolete**.

| Previous (feature-018 / draft-019) | Current (this spec) |
| --- | --- |
| `POST .../estimate` body: `{ "user_message": "..." }` | Body: **`EstimationRequest`** (same as `/api/v1/estimate`) |
| Metadata via LLM extractor from chat turns | **Deterministic** sync: latest form snapshot on session; optional LLM extractor **only** for attachment-only signals |
| Attachment block in **system** prompt | Attachment block in **user** prompt (with guided form body) |
| No session listing API | **`GET /api/v1/sessions`** lists all sessions |
| No Langfuse on session routes | **Langfuse traces** aligned with v2 estimator pattern |

`POST /api/v1/estimate` and `POST /api/v2/estimate` remain **stateless** (no session store). Session behavior is **only** under `/api/v1/sessions/*`.

### Already shipped (feature-018)

| Component | Location | Change in this feature |
| --- | --- | --- |
| `ConversationHistory` | `app/services/sessions.py` | Keep; store **compact** user turn labels per submit, not full guided Markdown |
| `ProjectMetadata` | `app/services/sessions.py` | Keep for compact distilled facts **or** derive display from `last_estimation_request` (see FR-04) |
| `Session` / `InMemorySessionStore` | `app/services/sessions.py` | Add `last_estimation_request`, `list_sessions()`, optional `submit_count` |
| `ConversationalEstimationService` | `app/services/conversational_estimation_service.py` | **Rename/refactor** to session guided orchestrator (name TBD: `SessionEstimationService`) |
| `render_session_system_prompt` | `app/services/estimation_prompt_rendering.py` | Metadata from **latest form**; **no** attachment block in system |
| `POST /api/v1/sessions/{id}/estimate` | `app/routers/sessions.py` | **Breaking:** accept `EstimationRequest`, not `SessionEstimateRequest` |
| Langfuse on v2 | `app/routers/estimations_v2.py` | **Reuse pattern** for session routes |

### Learnings (carry forward)

- Use `complete_structured` from `structured_llm_client` (no `acomplete_structured`).
- Run `uv run pytest --collect-only` before registering new routes.
- `system_prompt_override` + composed **user** prompt for `EstimationService.estimate()`.
- Do not store full attachment text in `ConversationHistory`.

## Scope

### Includes

- **`GET /api/v1/sessions`** — list all in-memory sessions (summary view).
- **`POST /api/v1/sessions/{session_id}/estimate`** — body `EstimationRequest` (JSON); supports **N submits** per session.
- Session orchestration: load session → sync form snapshot → extract attachments → compose prompts → estimate → update history → update session timestamps.
- **`Session.last_estimation_request`** — canonical “project memory” from the latest successful submit (all structured form fields).
- **Deterministic** `sync_session_from_request(session, request)` (map form → session fields / metadata rendering context).
- **Optional** LLM metadata extractor call only when attachment extracted text is non-empty (attachment signals); skip when submit has no new attachment content.
- `app/services/document_extractor.py` — TXT, PDF, DOCX extraction; DOC fails explicitly.
- `app/services/dynamic_context_manager.py` — bounded delimited block for **user** prompt.
- Extend `decode_attachment_notes` behavior for session path: real PDF/DOCX text extraction (not filename-only stub).
- New Jinja partial (recommended): `session_user_turn.md.j2` — `user_message` + `<attachments>` block; **or** Python composition mirroring guided_request + attachments pattern from product docs.
- Extend `session_project_metadata.md.j2` (or render from `build_request_render_context(last_request)`) so system prompt reflects **populated form fields only**.
- Langfuse: traces/spans on `POST /sessions`, `GET /sessions`, `POST /sessions/{id}/estimate` with `TelemetryContext.session_id` = path/store id.
- Config: `MAX_ATTACHMENT_SIZE_BYTES` (10 MB), `MAX_ATTACHMENT_CONTEXT_CHARS` (128k), `ALLOWED_ATTACHMENT_MIME_TYPES`.
- Align `app/schemas/estimation_request.py` attachment byte limits with **10 MB** (replace 256 KiB / 512 KiB totals).
- Session estimate returns **`EstimationResponse`** via `LLMPipeline` + `assemble_estimation_v2_response` (reuse v2 path).
- Tests and README updates.
- Deprecate/remove **`SessionEstimateRequest`** free-text-only contract.

### Excludes

- Persistence (DB, Redis, filesystem) for session state.
- Replacing or removing stateless `/api/v1/estimate` / `/api/v2/estimate`.
- Free-text-only session turns (no `user_message`-only API).
- Storing raw attachment bytes in session state.
- Full RAG / chunking (extension point only).
- **Pagination** on `GET /api/v1/sessions` (unbounded list for MVP).
- `GET /api/v1/sessions/{session_id}` detail endpoint (optional follow-up unless needed by UI).
- Background TTL cleanup (optional TODO on store).

## Functional Requirements

### FR-01: Session lifecycle

**Create**

- `POST /api/v1/sessions` → **201** `{ "session_id": "<uuid>" }`.
- Initializes empty history, empty `last_estimation_request`, default `project_metadata`.

**List**

- `GET /api/v1/sessions` → **200** with a JSON array of session summaries.
- Each summary includes at minimum: `session_id`, `created_at`, `updated_at`, `submit_count` (number of estimate calls completed), and optionally `project_name` from last form if present.
- Order: `updated_at` descending (most recently active first).
- **No pagination** in this iteration (unbounded list acceptable for in-memory MVP).
- Implementation: `InMemorySessionStore.list_sessions()` — encapsulated; no raw dict access outside `sessions.py`.

**Estimate (multi-submit)**

- `POST /api/v1/sessions/{session_id}/estimate` → body **`EstimationRequest`** (`application/json`), same schema as guided `/api/v1/estimate`.
- **404** if `session_id` unknown.
- Client may call **N times**; each call is one “submit” that appends history and replaces `last_estimation_request`.
- Response: **`EstimationResponse`** (structured JSON, same contract as `POST /api/v2/estimate`) via `LLMPipeline.run_structured` + `assemble_estimation_v2_response`.

**Breaking change:** `SessionEstimateRequest` (`user_message` only) is **removed** from this endpoint. Document in README.

### FR-02: Orchestration service owns context

A dedicated orchestrator (refactor of `ConversationalEstimationService`) performs **all** session context management:

1. Load session from store.
2. `sync_session_from_request(session, request)` — update `last_estimation_request`, merge deterministic fields into `project_metadata` where useful for compact display.
3. Extract text from `request.attachments` (base64) via `DocumentTextExtractor` when MIME is supported.
4. Build `dynamic_context_block` via `DynamicContextManager` (may be empty).
5. Build **system prompt**: `build_system_prompt(...)` + `render_session_system_prompt(base, session)` using latest form context (no attachment text in system).
6. Build **user prompt**: `render_guided_user_message(request)` + append dynamic attachment block (delimited, bounded). Do **not** duplicate attachment bodies inside `guided_request.md.j2` raw notes when extracted text is injected separately (avoid double injection).
7. History: `add_user_message(compact_turn_label)` — e.g. `"[Form submit] {project_summary}"` truncated; **not** full guided Markdown, **not** attachment text.
8. `LLMPipeline.run_structured(request, ...)` with composed system/user prompts (same structured path as v2; not markdown `estimate()`).
9. `add_assistant_message(serialized_estimation_summary)` — compact text derived from structured result for history (e.g. title + summary), not raw JSON blob.
10. Optional: `extract_and_merge_metadata` **only if** attachment extracted text non-empty (attachment signals cap 800 chars).
11. `session.updated_at = now`, increment `submit_count`.

### FR-03: Project memory = latest guided form

- **`Session.last_estimation_request: EstimationRequest | None`** is the **canonical structured memory** of the project for the session.
- System prompt metadata section is rendered from this snapshot (populated fields only; never `None` placeholders).
- Narrow `ProjectMetadata` may remain for distilled cross-submit facts or be derived from `last_estimation_request` for listing GET — implementer chooses **one source of truth**; prefer **`last_estimation_request`** for form parity to avoid drift.
- Sliding-window **history** does not replace form memory: even when old turns are trimmed, `last_estimation_request` and metadata rendering stay intact.

### FR-04: Conversation history

- Reuse `ConversationHistory` (`max_turns` default 10).
- System prompt message updated each submit (composed system).
- User/assistant pairs per submit; trim oldest pairs when over window.
- `to_messages_list()` is available for future multi-message provider APIs; v1 may still send single user string per `estimate()` — document as in feature-018 learnings.

### FR-05: Attachment extraction

For each `Attachment` on `EstimationRequest`:

| MIME | Strategy |
| --- | --- |
| `text/plain`, `text/markdown` | UTF-8 decode |
| `application/pdf` | `pypdf` page text + delimiters |
| `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | `python-docx` |
| `application/msword` | **422** explicit unsupported (convert to docx) |

Enforce `ALLOWED_ATTACHMENT_MIME_TYPES` and **`MAX_ATTACHMENT_SIZE_BYTES` (10 MB)** on **decoded** file bytes before extraction.

**Two limits (decided):**

| Limit | Value | Applies to |
| --- | --- | --- |
| Uploaded file (decoded) | **10 MB** (`MAX_ATTACHMENT_SIZE_BYTES`) | Raw attachment bytes in `EstimationRequest.attachments` |
| Extracted text in prompt | **128 000 characters** (`MAX_ATTACHMENT_CONTEXT_CHARS`) | Text after extraction, before LLM |

Raise `EstimationRequest` schema attachment caps from legacy **256 KiB** to **10 MB** so JSON/base64 uploads match the env limit (update `_MAX_ATTACHMENT_BYTES` / totals in `estimation_request.py`).

### FR-06: Dynamic context in **user** prompt

`DynamicContextManager.build_context_block(...)` returns:

```text
<attachments>
<attachment filename="spec.pdf">
... extracted text ...
</attachment>
</attachments>
```

Or equivalent `--- EXTERNAL CONTEXT ---` delimiters (pick one style; document in README). Prepend/append to guided user body with instruction: supporting material, not instructions.

- Budget: `MAX_ATTACHMENT_CONTEXT_CHARS` (default **`131_072`** = 128k characters). Truncate with marker when combined extracted text exceeds this cap (extracted text is usually far smaller than the binary file).
- Not stored in `ConversationHistory`.
- Not merged into system instructions.

### FR-07: Langfuse telemetry

Mirror `app/routers/estimations_v2.py` patterns (`get_observability()`, `TelemetryContext`, `start_trace`, `start_span`).

| Route | Trace name (suggested) | `session_id` in telemetry |
| --- | --- | --- |
| `POST /api/v1/sessions` | `estimator.api.v1.session_create` | new store id |
| `GET /api/v1/sessions` | `estimator.api.v1.session_list` | none or omit |
| `POST /api/v1/sessions/{id}/estimate` | `estimator.api.v1.session_estimate` | **path `{session_id}`** |

For estimate:

- `TelemetryContext(request_id=..., feature="estimation", session_id=<store uuid>, tags=[...])`
- Spans (suggested): `session.load`, `attachment.extract`, `prompt.compose`, `estimator.estimate`, `metadata.sync` (and `metadata.extract` if LLM path runs)
- On HTTP errors: `observability.set_http_status(...)` like v2
- Propagate `prompt_version` / `examples_version` via `set_prompt_context` when estimation runs
- **Do not** use `resolve_session_id(request)` header minting for Langfuse when store `session_id` is known—use the **store id** so all submits group in Langfuse Sessions UI

When observability export is disabled, behavior is unchanged (noop adapter).

### FR-08: Configuration

```python
max_attachment_size_bytes: int = 10_485_760   # 10 MB per decoded attachment file
max_attachment_context_chars: int = 131_072   # 128k chars of extracted text in user prompt
allowed_attachment_mime_types: list[str]  # comma-separated in .env
```

**Decided:** binary upload up to **10 MB**; only **extracted plain text** enters the prompt, capped at **128k characters**. Update `estimation_request.py` validators to allow 10 MB decoded attachments (replacing 256 KiB). Document both limits in README and `.env.example`.

### FR-09: Error surface

| Condition | HTTP |
| --- | --- |
| Unknown session | 404 |
| Unsupported MIME | 422 `UNSUPPORTED_MIME_TYPE` |
| File too large | 413 `ATTACHMENT_TOO_LARGE` |
| Extraction failure | 422 `EXTRACTION_FAILED` |
| Legacy `.doc` | 422 `UNSUPPORTED_FORMAT` |
| Guardrail / estimation / metadata errors | Same as existing estimations |

## Technical Approach

```text
Client
  POST /sessions                          → session_id
  GET  /sessions                          → [{ session_id, created_at, updated_at, ... }]
  POST /sessions/{session_id}/estimate    → EstimationRequest (JSON), repeatable

routers/sessions.py
  → observability.start_trace(...)
  → SessionEstimationService.run_submit(session_id, request)

SessionEstimationService
  → store.get_session
  → sync_session_from_request
  → DocumentTextExtractor (per attachment)
  → DynamicContextManager → user attachment block
  → render_guided_user_message(request) + attachment block  → user_prompt
  → build_system_prompt + render_session_system_prompt(..., last_request) → system
  → history.add_user_message(compact label)
  → LLMPipeline.run_structured(...) → EstimationResponse
  → history.add_assistant_message(compact summary)
  → optional extract_and_merge_metadata (attachments only)
  → store list/get updated
```

### Response schemas (new)

`SessionSummary` (for GET list):

- `session_id: str`
- `created_at: datetime`
- `updated_at: datetime`
- `submit_count: int`
- `project_name: str | None` (from `last_estimation_request.project_name` if any)

### Files (planned)

| File | Action |
| --- | --- |
| `app/services/sessions.py` | `last_estimation_request`, `submit_count`, `list_sessions()` |
| `app/schemas/session_estimation.py` | `SessionSummary`, remove/replace `SessionEstimateRequest` |
| `app/services/session_estimation_service.py` | New or rename from conversational |
| `app/services/document_extractor.py` | New |
| `app/services/dynamic_context_manager.py` | New |
| `app/services/session_sync.py` | New — map `EstimationRequest` → session/memory |
| `app/routers/sessions.py` | GET list, estimate with `EstimationRequest`, `response_model=EstimationResponse`, Langfuse |
| `app/schemas/estimation_request.py` | Raise attachment size limits to 10 MB |
| `app/prompts/estimation/v2/partials/session_user_attachments.md.j2` | Optional |
| `app/prompts/estimation/v2/partials/session_project_metadata.md.j2` | Extend for form fields |
| `app/services/prompt_context.py` | Shared attachment extraction for session path |
| `app/config.py`, `.env.example`, `README.md` | Settings + docs |
| `app/main.py` | Register GET route in OpenAPI root hints |
| Tests | See Test Plan |

### Dependencies

```bash
uv add pypdf python-docx
```

### Prompt budget (per submit)

| Layer | Channel | Notes |
| --- | --- | --- |
| System instructions + examples | System | Static + mode |
| Session project facts (from last form) | System | Jinja metadata partial |
| Guided form body | User | `guided_request.md.j2` |
| Extracted attachments | User | Bounded block (≤ 128k chars) |
| History (if passed to provider later) | — | Trimmed pairs |
| Assistant prior turns | — | In session store, not re-sent in v1 single-user-string API |

## Acceptance Criteria

### Sessions API
- [ ] AC-01: `POST /api/v1/sessions` returns 201 with UUID.
- [ ] AC-02: `GET /api/v1/sessions` returns all sessions with summary fields; empty store returns `[]`.
- [ ] AC-03: Two creates yield distinct IDs.
- [ ] AC-04: `POST /api/v1/sessions/{id}/estimate` with valid `EstimationRequest` returns 200 and **`EstimationResponse`** (structured JSON).
- [ ] AC-05: Second submit same session updates `updated_at`, increments `submit_count`, appends history.
- [ ] AC-06: Unknown session id → 404.
- [ ] AC-07: Free-text-only `SessionEstimateRequest` is no longer accepted (400/422 or removed schema).

### Form + memory
- [ ] AC-08: After submit, `session.last_estimation_request` equals submitted request (modulo normalization).
- [ ] AC-09: System prompt includes populated form fields from latest submit; no `None` placeholders.
- [ ] AC-10: After history trim, `last_estimation_request` unchanged.
- [ ] AC-11: History user messages do not contain full attachment extracted text.

### Attachments
- [ ] AC-12: PDF/DOCX/TXT attachments extracted to text; injected in **user** prompt block.
- [ ] AC-13: Unsupported MIME → 422.
- [ ] AC-14: Oversize → 413.
- [ ] AC-15: `.doc` → 422 with conversion hint.
- [ ] AC-16: Truncation when extracted text exceeds **128k** (`MAX_ATTACHMENT_CONTEXT_CHARS`).
- [ ] AC-16b: Decoded attachment file up to **10 MB** accepted; over 10 MB → 413.
- [ ] AC-16c: `EstimationRequest` schema allows 10 MB decoded attachments (not 256 KiB).

### Langfuse
- [ ] AC-17: Session estimate trace uses store `session_id` in `TelemetryContext`.
- [ ] AC-18: With export enabled, trace/spans visible (mock test like `test_estimations_v2_observability.py`).
- [ ] AC-19: Failed estimate sets HTTP status on observability span.

### Regression
- [ ] AC-20: `uv run pytest` full suite green.
- [ ] AC-21: `uv run pytest --collect-only` zero errors.
- [ ] AC-22: No secrets in repo.

## Test Plan

### Unit
- `test_sessions.py` — `list_sessions`, `last_estimation_request`, `submit_count`
- `test_session_sync.py` — form → session memory mapping
- `test_document_extractor.py` — MIME strategies
- `test_dynamic_context_manager.py` — budget, delimiters
- `test_session_estimation_service.py` — orchestration (mock estimate + store)
- `test_estimation_prompt_rendering.py` — system metadata from form; user attachment block not in system

### Integration
- `test_sessions_router.py` — POST create, GET list, POST estimate ×2, 404, Langfuse mock
- `test_sessions_router_observability.py` — optional dedicated file

### Manual

```bash
uv run uvicorn app.main:app --reload
SESSION=$(curl -s -X POST http://127.0.0.1:8000/api/v1/sessions | jq -r '.session_id')
curl -s http://127.0.0.1:8000/api/v1/sessions | jq
curl -s -X POST "http://127.0.0.1:8000/api/v1/sessions/$SESSION/estimate" \
  -H 'Content-Type: application/json' \
  -d @tests/fixtures/minimal_estimation_request.json | jq
```

## Verification

- **Automated:** scoped pytest modules above — **Not verified**
- **Regression:** `uv run pytest` — **Not verified**
- **Langfuse manual:** with export enabled, confirm traces grouped by `session_id` — **Not verified**

## Documentation Plan

- `README.md`: session workflow (create → list → submit form N times); breaking change on estimate body; Langfuse session grouping; attachment limits.
- `.env.example`: new attachment env vars.
- `app/main.py` root keys: `sessions_list`, updated `session_estimate` description.

## Implementation Plan

- [ ] Step 0: Raise `EstimationRequest` attachment limits to 10 MB + config defaults (128k text cap) + `test_estimation_request.py`.
- [ ] Step 1: Extend `Session` + store (`list_sessions`, `last_estimation_request`, `submit_count`) + tests.
- [ ] Step 2: `SessionSummary` schema + `GET /sessions` + Langfuse trace + router tests.
- [ ] Step 3: `document_extractor` + `dynamic_context_manager` + tests.
- [ ] Step 4: `session_sync` + extend metadata partial / rendering from form + tests.
- [ ] Step 5: Refactor orchestrator to `EstimationRequest` submit path + user-prompt attachment injection + tests.
- [ ] Step 6: Wire `POST .../estimate`, remove `SessionEstimateRequest`, Langfuse spans on estimate + integration tests.
- [ ] Step 7: README, `.env.example`, full pytest, sync AC.

## Estimation

- **Size:** L
- **Estimated time:** 6–8 hours
- **Planned steps:** 8

## Implementation progress

- [ ] Step 0: Raise `EstimationRequest` attachment limits + config defaults (`MAX_ATTACHMENT_*`)
- [ ] Step 1: Extend `Session` + `InMemorySessionStore.list_sessions()` + tests
- [ ] Step 2: `SessionSummary` + `GET /api/v1/sessions` + Langfuse trace + router tests
- [ ] Step 3: `document_extractor` + `dynamic_context_manager` + deps + unit tests
- [ ] Step 4: `session_sync` + metadata partial from form + rendering tests
- [ ] Step 5: `SessionEstimationService` guided submit orchestration + unit tests
- [ ] Step 6: Wire `POST .../estimate` (`EstimationRequest` / `EstimationResponse`), remove `SessionEstimateRequest`, Langfuse spans
- [ ] Step 7: README, `.env.example`, full `uv run pytest`, sync AC

## Pull Request

- **WIP draft:** https://github.com/povedica/master-ia-lidr/pull/16 (label `wip`)

---

## Architecture Note A — Form snapshot vs chat metadata

**Why `last_estimation_request` instead of only six extractor fields**

The guided form already captures structured project facts. Copying them into a small `ProjectMetadata` via LLM on every submit duplicates information and risks drift. The session stores the **latest `EstimationRequest`** and renders the system metadata block from that snapshot (populated fields only). The LLM extractor becomes **optional** and attachment-focused, reducing cost and latency on typical submits.

**Why history still matters with full form resubmits**

Each submit may change few fields; history gives the model short **turn labels** and prior assistant estimates for refinement (“increase buffer”, “drop mobile scope”). The full brief is still in the current user prompt via `guided_request.md.j2`; history is not the primary brief carrier.

---

## Architecture Note B — Attachments in user prompt

External documents are **user-provided input** for the current submit, not system policy. Delimited blocks in the **user** prompt match the product pattern (`<transcript>` / `<attachments>`) and reduce prompt-injection risk versus placing untrusted text in system instructions. `guided_request.md.j2` may still list attachment filenames in “Documentos de apoyo”; extracted text lives only in the separate bounded block to avoid duplication—implementer should disable redundant `attachment_notes` body text when extraction succeeds.

---

## Architecture Note C — Langfuse session grouping

Using the **in-memory store UUID** as Langfuse `session_id` groups all submits from one browser workflow. Header `X-Session-Id` on stateless routes remains independent (telemetry-only minting). Do not conflate the two ids in docs or code.

---

## Design Decisions

| Decision | Rationale |
| --- | --- |
| `EstimationRequest` on session estimate | Same form as stateless estimator; frontend submits once per session iteration. |
| **`EstimationResponse` on session estimate** | Align with v2 structured estimator; single JSON contract for UI. |
| **10 MB file / 128k extracted text** | Large binaries allowed at upload; prompt only carries bounded plain text (~128k chars max). |
| Raise schema attachment caps to 10 MB | Avoid 256 KiB Pydantic rejection before extraction. |
| User prompt carries attachments | Safer and semantically correct vs system prompt. |
| `GET /sessions` without pagination | In-memory MVP; full list is acceptable for now. |
| Langfuse store `session_id` | Correlates N submits in one trace session. |
| Compact history labels | Avoid token explosion from full guided Markdown × turns. |
| Breaking removal of free-text session body | Product does not want conversational mode. |
