# Feature: Session Exercise Completion — Multipart Submit, LLM Memory Wiring, Metadata Merge, README

## Objective

Close the remaining gaps between the **session exercise “done” criteria** and the current codebase (`feature-020` simplified contract, `feature-022` integration tests). Today:

| Criterion | Current state |
| --- | --- |
| `POST /api/v1/sessions` → `session_id` | **Done** |
| `POST .../estimate` with **multipart/form-data**, transcript, optional attachments, Pydantic estimate | **Not done** (JSON + base64 only) |
| Multi-turn LLM coherence (project name not “forgotten”) | **Partial** (metadata in system prompt; **history not sent** to `complete_structured`) |
| `project_metadata` updates visibly between turns | **Partial** (re-derived per submit; **no merge** with prior session memory) |
| Sliding window on history | **Done** in `ConversationHistory` |
| README: attachment path + why + metadata extraction | **Partial** (Path B named; **no explicit “why”**; metadata note only in integration subsection) |

This feature makes every row **complete** without replacing the simplified JSON contract the web UI already uses.

## Context

### Shipped baseline

| Area | Location |
| --- | --- |
| Session store + sliding window | `app/services/sessions.py` — `ConversationHistory`, `ProjectMetadata`, `DerivedProjectMetadata` |
| HTTP routes | `app/routers/sessions.py` — `POST /sessions`, `POST /sessions/{id}/estimate` (JSON body) |
| Orchestration | `app/services/simplified_session_estimation_service.py` |
| Heuristic metadata | `app/services/simplified_session_metadata.py` — `derive_project_metadata()` |
| Attachments (Path B) | `app/services/simplified_attachment_processing.py`, `app/services/document_extractor.py` |
| Structured LLM | `app/services/structured_llm_client.py` — `complete_structured(system_prompt, user_prompt)` (single user turn) |
| Prompt metadata block | `app/services/estimation_prompt_rendering.py` — `render_session_system_prompt()` |
| Integration tests | `tests/test_sessions_integration.py` (JSON only; fake `complete_structured`) |
| Web client | `web/src/features/estimation/api/sessionApi.ts` — `estimateInSession` sends JSON |

### Related but out of scope for this feature’s primary path

- `ConversationalEstimationService` + `metadata_extractor.py` (LLM merge into `ProjectMetadata`) exist but are **not wired** to HTTP. Reuse patterns only; do not expose a second estimate contract.
- **Path A** (provider Files API) was explicitly deferred in `feature-022`.

### Exercise vs product

The exercise text asks for **multipart** and multi-turn memory. Production (`feature-020`/`021`) standardized on **JSON + `AttachmentRef.content_base64`**. This feature adds multipart as a **first-class alternate transport** on the **same** estimate URL and keeps JSON for backward compatibility.

## Scope

### Includes

- **Content negotiation** on `POST /api/v1/sessions/{session_id}/estimate`:
  - `application/json` → existing `SessionEstimateRequest` (unchanged field semantics).
  - `multipart/form-data` → same logical submit (transcript, core fields, optional files).
- **Path B only** for multipart files: local extraction via `DocumentTextExtractor` (same limits/MIME rules as `AttachmentRef`).
- **Wire session memory into the structured LLM call** so prior turns influence the model (not only the latest system prompt).
- **Merge session `project_metadata` across turns** for simplified submits (heuristic merge of `DerivedProjectMetadata` + compact `ProjectMetadata` on `Session`).
- **Optional `project_name` on later turns** when session already has derived metadata (multipart and JSON).
- **Integration tests** for multipart, metadata delta between turns, and LLM message list assertions (extend `FakeStructuredLLM` if needed).
- **README** subsection: attachment path decision (**why Path B**, why not Path A), how `project_metadata` is built and merged.
- **Web** (minimal): `estimateInSession` can send `FormData` when files are present (keep JSON when no files) — required for end-to-end multipart verification.

### Excludes

- OpenAI / Anthropic **Files API** (Path A) and pre-registered `file_id` upload service.
- Database/Redis session persistence.
- Replacing heuristic metadata with LLM extractor (`metadata_extractor`) — optional follow-up `feature-024` if product wants extractor on simplified path.
- Changing stateless `/api/v1/estimate` or `/api/v2/estimate` contracts.
- E2E browser tests (Playwright).
- New session routes beyond the existing estimate URL.

## Functional Requirements

### FR-01: Session creation (unchanged)

- `POST /api/v1/sessions` returns **201** with `{ "session_id": "<uuid>" }`.
- No regression to `tests/test_sessions_integration.py::test_create_session_initializes_empty_state`.

### FR-02: Multipart estimate submit

When `Content-Type` is `multipart/form-data`, `POST /api/v1/sessions/{session_id}/estimate` accepts:

| Part | Required | Notes |
| --- | --- | --- |
| `transcript` | Yes | Same min length as JSON (`_TRANSCRIPT_MIN` = 80 after trim) |
| `project_name` | Yes on first submit; optional later (FR-05) | Form string |
| `project_type` | Yes | Enum string matching `ProjectType` |
| `target_audience` | Yes | Enum string matching `TargetAudience` |
| `industry` | No | Optional enum |
| `one_line_summary` | No | Optional |
| `additional_extra_info` | No | Optional |
| `attachments` | No | Repeatable file parts **or** a single part with multiple files — pick one convention and document in OpenAPI/README (recommend: repeated field name `attachments`) |

Rules:

- Reject unsupported MIME types and oversize files with the same codes/limits as `AttachmentRef` (`app/schemas/estimation_request.py` shared constants).
- Map uploaded files to internal `AttachmentRef`-equivalent processing (generate `file_id` per file, e.g. `upload-{index}`) before `process_attachment_refs()`.
- Response body remains **`SessionEstimateResponse`** (same Pydantic models as JSON path).
- **404** if `session_id` missing; validation errors **422** with stable shape.

### FR-03: JSON estimate submit (backward compatible)

- `Content-Type: application/json` continues to accept `SessionEstimateRequest`.
- No breaking changes to field names or response envelope used by `web/` and `tests/test_sessions_integration.py`.

### FR-04: Structured estimate shape

- Both transports must return `estimate` serialized from `assemble_estimation_v2_response()` (same core shape as `POST /api/v2/estimate`).
- OpenAPI/Swagger must document both request content types on the estimate operation.

### FR-05: Multi-turn field defaults

On submit **after** the session has `last_derived_metadata`:

- If `project_name` is omitted (multipart) or empty (JSON), use `session.last_derived_metadata.project_name`.
- If `project_type` / `target_audience` omitted, use last derived values (document in README).
- First submit in a session still requires explicit core fields.

### FR-06: LLM receives conversation history

For each simplified session submit:

1. Build `composed_system` with `render_session_system_prompt(..., session.project_metadata)` (use **merged** metadata from FR-07 before render).
2. Set system prompt on `session.conversation_history`.
3. Build **current** `user_prompt` (guided message + attachment block) as today.
4. Call structured estimation with **full chat messages**:
   - `messages = session.conversation_history.to_messages_list()` **plus** `{"role":"user","content": user_prompt}` for the current turn.
   - Do **not** duplicate the current user message inside history before the call.
5. On success, append to history:
   - user: compact turn label `[Simplified submit] {project_name}` (keep window small),
   - assistant: compact estimation summary (existing `_compact_estimation_summary`).
6. Extend `complete_structured()` (or a thin wrapper used only from `estimate_structured`) to accept `messages: list[dict[str, str]]` when provided; validate first message is `system`, last is `user`, roles alternate for prior pairs.

**Coherence acceptance:** After turn 1 establishes project name “Acme Portal”, turn 2 multipart/JSON with transcript mentioning only new scope (e.g. Redis) must still pass integration assertion that fake LLM `system_prompt` contains `Acme Portal` **and** message list length ≥ prior turns + 1 user message.

### FR-07: Merge `project_metadata` across turns

Introduce `merge_derived_metadata(previous: DerivedProjectMetadata | None, incoming: DerivedProjectMetadata) -> DerivedProjectMetadata`:

| Field | Merge rule |
| --- | --- |
| `project_name` | Keep `incoming` if non-empty; else `previous` |
| `project_type`, `target_audience`, `industry` | Same as scalars |
| `summary` | Prefer `incoming.one_line_summary` or new transcript excerpt; if turn adds attachment-only signal, update |
| `detected_constraints` | Union by normalized line text, cap 5 |
| `attachment_summary` | Replace with latest non-empty processed summary |
| `confidence_notes` | Append new warnings, dedupe |

After merge:

- Persist `session.last_derived_metadata` and `session.project_metadata` (`_derived_to_project_metadata`).
- Response `project_metadata` is the **merged** object.

**Visible update:** Turn 2 must change at least one of `summary`, `detected_constraints`, or `attachment_summary` compared to turn 1 when transcript/attachments differ (covered by test).

### FR-08: Sliding window (no regression)

- `ConversationHistory._enforce_window()` behavior unchanged (default `max_turns=10`).
- Existing `test_sliding_window_drops_oldest_pairs_preserves_system_prompt` stays green.
- With FR-06, trimming affects what prior turns the LLM sees — test still asserts oldest markers dropped.

### FR-09: README documentation

Expand root `README.md` **Simplified session estimation** (not only the integration-test subsection):

1. **Attachment strategy:** Path B (local extraction); **why** (no external file store, deterministic tests, no Files API keys/quota, works with current in-memory sessions).
2. **Why not Path A** for now (follow-up only if product needs provider-native files).
3. **Transports:** JSON base64 for SPA; multipart for exercise/clients uploading files directly.
4. **Metadata:** heuristic `derive_project_metadata()` per submit + `merge_derived_metadata()` across turns; not LLM extractor on this path.
5. **Memory:** system prompt metadata block + bounded `conversation_history` passed to structured LLM.

Optional one-line cross-link in `docs/technical/README.md` (no duplicate spec).

### FR-10: Web client (minimal)

- When the simplified form has no `File` objects, keep JSON `estimateInSession`.
- When the user attaches files, build `FormData` (same field names as FR-02) and POST without `Content-Type: application/json` (browser sets boundary).
- No change to session create/list/detail.

## Technical Approach

### Request parsing

Add `app/services/session_estimate_request_parser.py` (or `app/schemas/session_multipart.py`):

```text
async def parse_session_estimate_request(request: Request) -> SessionEstimateRequest:
    if content-type is multipart → read Form + UploadFile → SessionEstimateRequest
    else → await request.json() → SessionEstimateRequest.model_validate(...)
```

Router `estimate_in_session` depends on this parser instead of a bare `body: SessionEstimateRequest` parameter.

### LLM message plumbing

```text
app/services/structured_llm_client.py
  complete_structured(..., messages: list[dict[str, str]] | None = None)

app/services/llm_service.py
  estimate_structured(..., messages_override: list[dict[str, str]] | None = None)

app/guardrails/llm_pipeline.py
  run_structured(..., messages_override=...)

app/services/simplified_session_estimation_service.py
  build messages_override from session.conversation_history + current user_prompt
```

Pass `messages_override` into `LLMPipeline.run_structured` / `estimate_structured`; when set, **ignore** separate `user_prompt_override` for the litellm call (still use overrides to build the final user message content).

### Metadata merge

- New module: `app/services/simplified_session_metadata_merge.py` with `merge_derived_metadata`.
- `derive_project_metadata()` stays per-submit; merge runs immediately after derive.

### Multipart → attachments

- `multipart_attachments.py`: convert `UploadFile` → bytes → `AttachmentRef(file_id=..., name=..., mime_type=..., content_base64=...)`.
- Reuse `process_attachment_refs()` unchanged.

### OpenAPI

- Use FastAPI `responses` / duplicate body documentation or `openapi_extra` for multipart schema.
- Verify `/docs` shows both content types.

### Data flow (one submit)

```text
HTTP (JSON | multipart)
  → parse → SessionEstimateRequest
  → load Session
  → merge defaults from session.last_derived_metadata (FR-05)
  → process_attachment_refs
  → derive_project_metadata
  → merge_derived_metadata(session.last_derived_metadata, derived)
  → adapt_to_estimation_request + render prompts
  → messages = history + current user
  → LLMPipeline.run_structured(messages_override=...)
  → append compact turns to history
  → persist session + SessionEstimateResponse
```

## Acceptance Criteria

- [ ] **AC-01:** `POST /api/v1/sessions` returns `201` and UUID `session_id` (regression).
- [ ] **AC-02:** Same estimate URL accepts `multipart/form-data` with `transcript` + required fields and optional file parts; returns `200` + `SessionEstimateResponse`.
- [ ] **AC-03:** JSON submit on same URL unchanged for existing integration tests (no regressions).
- [ ] **AC-04:** Multipart upload with `text/plain` attachment containing `ATTACH_MARKER:USE_REDIS` reaches LLM user content and updates `attachment_summary` (mirror `test_attachment_text_influences_llm_prompt_and_estimate` with multipart helper).
- [ ] **AC-05:** Two linked submits: turn 2 omits `project_name` in multipart (or JSON); response and fake LLM `system_prompt` still contain turn-1 project name.
- [ ] **AC-06:** Fake LLM receives **more than one** user message in `messages` after turn 2 (history wired).
- [ ] **AC-07:** Turn 2 `project_metadata` differs from turn 1 in at least one field (`detected_constraints`, `summary`, or `attachment_summary`) when transcript changes.
- [ ] **AC-08:** Seven submits with `max_turns=3` still drop oldest markers; `project_metadata.project_name` preserved.
- [ ] **AC-09:** `estimate` in response validates against existing v2 assembler output shape (existing tests / schema smoke).
- [ ] **AC-10:** README documents Path B choice, why, both transports, metadata derive + merge, and memory model.
- [ ] **AC-11:** Web sends `FormData` when files attached; JSON when not (manual or unit test on builder).
- [ ] **AC-12:** `uv run pytest tests/test_sessions_integration.py` and full `uv run pytest` green without real API keys.

## Test Plan

### Unit tests

- `tests/test_simplified_session_metadata_merge.py` — merge rules, caps, empty previous.
- `tests/test_session_multipart_parser.py` — form fields, file size/MIME rejection, enum parsing (use `TestClient` or Starlette Request factory).
- `tests/test_structured_llm_messages.py` (optional) — `complete_structured` with 3+ messages mocked.

### Integration tests (`tests/test_sessions_integration.py`)

- `test_multipart_submit_with_attachment` — positive Path B.
- `test_multipart_second_turn_omits_project_name` — FR-05 + FR-06.
- `test_metadata_changes_between_turns` — FR-07.
- Extend `FakeStructuredLLM` to capture `messages` argument (add field on fake call record); assert length and roles.

### Manual checks

1. `uv run uvicorn app.main:app --reload`
2. Swagger: submit estimate with multipart.
3. Web UI: attach `.txt` file, two submits, confirm metadata panel updates and project name persists.

## Verification

- **Automated:** `uv run pytest tests/test_sessions_integration.py`; `uv run pytest`; `uv run pytest tests/test_session_multipart_parser.py` (if split).
- **Manual:** Swagger multipart + web FormData path; inspect metadata panel between turns.
- **Not verified yet:** Path A Files API, load testing, multi-worker session affinity.

## Documentation Plan

- `README.md` — FR-09 content in **Simplified session estimation**.
- `docs/technical/README.md` — one cross-link to session multipart + memory (no full duplicate).
- Update `feature-022` verification note only if needed after merge (optional).
- `web/README.md` — one sentence on FormData when files present.

## Implementation Plan

- [ ] **Step 1:** `merge_derived_metadata` + unit tests (RED → GREEN).
- [ ] **Step 2:** Extend `complete_structured` / `estimate_structured` / pipeline with `messages_override` + unit/fake test.
- [ ] **Step 3:** Wire `SimplifiedSessionEstimationService` to build `messages_override`, FR-05 defaults, merge after derive; extend integration test for AC-05/06/07.
- [x] **Step 4:** Multipart parser + router content negotiation + unit tests (RED → GREEN).
- [x] **Step 5:** Integration tests for multipart attachment (AC-04); full module green.
- [x] **Step 6:** README + technical cross-link + OpenAPI check.
- [x] **Step 7:** Web `FormData` path + `web/README.md`; manual smoke.

## Learnings

| Pitfall | Prevention |
| --- | --- |
| Implementing during `/write-feature` | Spec only here; code via `/start-task` |
| Inventing `acomplete_structured` | Patch/call `complete_structured` only |
| Duplicating current user in history **and** messages list | Append to history **after** LLM success only |
| Breaking JSON clients | Keep JSON path; add negotiation, not a new URL |
| Mocking entire `SimplifiedSessionEstimationService` in integration tests | Extend `tests/test_sessions_integration.py` + fake at `complete_structured` |
| Switching to Path A mid-feature | Explicitly out of scope; document why in README |
| Replacing compact history with full transcript | Keep compact pairs in store; full text only in final user message of `messages_override` |

## Estimation

- Size: **L**
- Estimated time: 6–8 hours
- Planned steps: 7

## Implementation progress

- [x] Step 1: `merge_derived_metadata` + unit tests
- [x] Step 2: `messages_override` through structured LLM / pipeline
- [x] Step 3: Wire `SimplifiedSessionEstimationService` (FR-05/06/07) + integration assertions
- [x] Step 4: Multipart parser + router content negotiation + unit tests
- [x] Step 5: Multipart integration tests (AC-04)
- [x] Step 6: README + technical cross-link + OpenAPI check
- [x] Step 7: Web `FormData` path + `web/README.md`

## Pull Request

- Draft: https://github.com/povedica/master-ia-lidr/pull/20 (label: `wip`)
