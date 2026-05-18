# Feature: Conversational Memory — Sliding Window + Distilled Project Metadata

## Objective

Evolve the estimator AI service from a transactional endpoint into a **multi-turn conversational estimator** with explicit separation between:

1. **Conversation history** — raw chronological messages, sliding window, system prompt always preserved.
2. **Project metadata** — distilled typed facts, stored separately, survive history truncation, injected into every system prompt, updated after each turn via an **LLM extractor**.

Wire feature-017 domain types into HTTP endpoints, prompt rendering, and a dedicated orchestration layer. **Do not** collapse history and metadata into one growing text blob.

## Context

### Already shipped (feature-017, merged)

`app/services/sessions.py` provides:

| Type | Role |
| --- | --- |
| `ChatMessage` | Frozen `role` + `content` |
| `ConversationHistory` | `max_turns` (default 10), `set_system_prompt`, `add_*`, `to_messages_list()` → `list[dict[str, str]]` |
| `ProjectMetadata` | `project_name`, `assumed_team_size`, `mentioned_technologies`, `agreed_scope` (all optional) |
| `Session` | `session_id`, `created_at`, `conversation_history`, `project_metadata` |
| `InMemorySessionStore` | `create_session`, `get_session`, `exists`, `delete_session` |
| `session_store` | Module singleton |

`tests/test_sessions.py` — 9 unit tests, all green on `main`.

### Current estimation stack (unchanged by feature-017)

- Routes: `app/routers/estimations.py` (`POST /api/v1/estimate`), `estimations_v2.py`.
- Service: `EstimationService` in `app/services/llm_service.py` — guided form, guardrails, cache, `render_estimation_prompt()`.
- Structured LLM: `complete_structured()` in `app/services/structured_llm_client.py` (Instructor + LiteLLM). Signature requires `litellm_model`, `chain_provider`, `api_key`, `timeout_seconds`, `system_prompt`, `user_prompt`, `max_output_tokens`, `response_model`, `max_attempts`. **There is no `acomplete_structured` helper.**
- Prompts: `app/services/estimation_prompt_rendering.py` + Jinja bundles under `app/prompts/estimation/`.

### Learnings from a premature implementation attempt (2026-05-18)

The following mistakes were made when code was written during `/write-feature` instead of `/start-task`. **Do not repeat:**

| Mistake | Impact | Correct approach |
| --- | --- | --- |
| Implemented code during `/write-feature` | Partial, untested feature; user expected spec only | **Only** edit `docs/work-items/` during `/write-feature`; run `/start-task` for code |
| Imported non-existent `acomplete_structured` | `ImportError` on `app.main` import; **3 test modules failed collection** | Use `complete_structured` with provider chain + settings (see `llm_service.py` ~748) |
| Registered `sessions` router before extractor worked | Entire API test suite blocked at import | Register router only after module imports cleanly; verify `uv run pytest --collect-only` |
| Stub assistant text in route handler | AC-05/07 not met; no real estimation | Thin router + `ConversationalEstimationService` calling `EstimationService` |
| `render_project_metadata_block` only in `sessions.py`, unused | AC-07 not met | Integrate via `estimation_prompt_rendering` or Jinja partial + tests |
| No `test_metadata_extractor.py` / `test_sessions_router.py` | AC-09–12 untested | TDD per `/start-task` hard stop |
| Merge logic without revision/removal | Doc promised removals; code only append/overwrite scalars | Define FR for merge; test explicit revisions |
| Renamed `conversation_history` → `history` without plan | Unnecessary churn vs feature-017 | Keep `conversation_history`; add `updated_at` only unless ADR says rename |

**Reverted state:** Only this work item exists on disk; no feature-018 application code remains on `main`.

## Scope

### Includes

- Extend `ProjectMetadata`: `explicit_constraints`, `rejected_options`.
- Extend `Session`: `updated_at` (UTC), touched on each estimate turn.
- `POST /api/v1/sessions` — create session, return `session_id`.
- `POST /api/v1/sessions/{session_id}/estimate` — conversational turn (see FR-02 for payload).
- `app/services/metadata_extractor.py` — LLM extractor + validated merge into `ProjectMetadata`.
- `app/services/conversational_estimation_service.py` (or equivalent) — orchestration: load session, compose prompts with metadata + history, call estimation, append turns, run extractor, persist in store.
- `app/routers/sessions.py` — thin HTTP layer only.
- Prompt integration: inject populated metadata into system prompt every turn (no `"None"` placeholders).
- Tests: domain extensions, extractor (mocked LLM), router integration (TestClient).
- README / root endpoint: document new routes.
- Architecture note in this document (LLM extractor vs heuristics) — keep § Architecture Decision below.

### Excludes

- Attachment handling in session context.
- Persistence (database, Redis, filesystem).
- Background TTL cleanup jobs (optional one-line TODO on store only if obvious).
- Unrelated refactors (guardrails, semantic cache, observability).
- Changing non-session `/api/v1/estimate` or `/api/v2/estimate` contracts unless required for shared prompt helpers.

## Functional Requirements

### FR-01: Session creation

- `POST /api/v1/sessions` returns **201 Created** with body `{ "session_id": "<uuid>" }`.
- Store initializes empty `ConversationHistory` and empty `ProjectMetadata`.
- Two consecutive creates return **different** UUIDs.

### FR-02: Conversational estimate turn

**Request (decision for implementer):** Prefer a dedicated schema, e.g. `SessionEstimateRequest`, containing:

- `user_message: str` (required) — free-text turn for the conversational path.
- Optional: reuse fields from `EstimationRequest` only if product needs guided-form fields in-session (default: **free-text only** for v1 of this feature to limit scope).

**Flow:**

1. Load session by `session_id`; **404** if missing.
2. Build system prompt = base estimation system + **metadata block** (populated fields only) + instruction to treat metadata as established facts unless the current turn revises them.
3. Ensure `conversation_history` has system prompt set (first turn or when template version changes — document rule in code).
4. Append user message to history **before** LLM call (or per product rule, but be consistent and tested).
5. Call existing estimation pipeline with messages = `history.to_messages_list()` + current user message (avoid duplicating user line).
6. Append assistant message (serialized estimation summary or structured response text — match existing API patterns).
7. Run metadata extractor (FR-03).
8. Update `session.updated_at`.
9. Return same response shape as existing estimate endpoints where practical (`EstimateResponse` / structured v2 — pick one and document in OpenAPI).

**Must not** return hardcoded placeholder assistant text.

### FR-03: LLM metadata extractor

**Inputs:** current `ProjectMetadata`, latest user turn, latest assistant turn.

**Mechanism:**

- Call `complete_structured()` with a narrow system prompt and `response_model=ProjectMetadata` (or a dedicated `ProjectMetadataUpdate` model if partial updates are clearer).
- Use provider chain + settings (same as estimation), not a fictional wrapper.

**Merge rules (post-validation):**

| Field kind | Rule |
| --- | --- |
| Scalars (`project_name`, `assumed_team_size`, `agreed_scope`) | Overwrite when extractor returns non-`None`; support **clear** when extractor returns `null` and user explicitly revoked fact (test with example) |
| Lists (`mentioned_technologies`, `explicit_constraints`, `rejected_options`) | Append new items case-insensitively without duplication; support **removal** when user clearly rejects a prior item (test with example) |

**On failure:** Raise or map to a **controlled HTTP error** (e.g. 503 with safe message) after retries — do not silently leave metadata unchanged unless product explicitly chooses fallback (if fallback, document in AC and test).

### FR-04: Prompt rendering

- Add a single tested entry point, e.g. `render_session_system_prompt(base_system: str, metadata: ProjectMetadata) -> str` in `estimation_prompt_rendering.py` or a Jinja partial fed by `build_prompt_render_context`.
- Include only populated metadata fields.
- Never emit `project_name: None` or similar placeholders.

### FR-05: History sliding window

- Reuse feature-017 `ConversationHistory` behavior: system prompt always first; drop oldest user/assistant **pairs** when `len(_turns) // 2 > max_turns`.
- `project_metadata` on the session **must not** be trimmed when history is trimmed (test AC-08).

### FR-06: Store encapsulation

- All session access via `InMemorySessionStore` methods; no raw `_sessions` dict access outside `sessions.py`.
- Optional `save(session)` only if mutation patterns require it; in-place mutation of stored `Session` is acceptable if documented.

## Technical Approach

```text
Client
  → POST /api/v1/sessions
  → POST /api/v1/sessions/{id}/estimate
       → routers/sessions.py (HTTP only)
       → conversational_estimation_service.py
            → sessions.session_store
            → estimation_prompt_rendering (metadata + system)
            → EstimationService / llm_service (existing)
            → metadata_extractor → complete_structured
       → response
```

**Files to create or modify (planned):**

| File | Action |
| --- | --- |
| `app/services/sessions.py` | Extend metadata + `updated_at` |
| `app/services/metadata_extractor.py` | New |
| `app/services/conversational_estimation_service.py` | New orchestrator |
| `app/routers/sessions.py` | New |
| `app/schemas/session_estimation.py` (or similar) | New request/response models |
| `app/services/estimation_prompt_rendering.py` | Metadata injection |
| `app/main.py` | Register router **after** imports verified |
| `tests/test_sessions.py` | Extend |
| `tests/test_metadata_extractor.py` | New |
| `tests/test_sessions_router.py` | New |
| `README.md` | New endpoints |

**Provider call pattern for extractor (reference):**

```python
# Pattern from llm_service.py — adapt with settings + build_provider_chain()
domain_result, raw_usage, finish = await complete_structured(
    litellm_model=litellm_model,
    chain_provider=provider.name,
    api_key=api_key,
    timeout_seconds=timeout,
    system_prompt=extraction_system,
    user_prompt=extraction_user,
    max_output_tokens=...,
    response_model=ProjectMetadata,
    max_attempts=settings.structured_output_max_attempts,
)
```

**Environment variables:** Reuse existing OpenAI/LiteLLM settings; no new secrets. If a cheaper model is desired for extraction, add optional `OPENAI_METADATA_MODEL` in a follow-up (out of scope unless needed).

## Acceptance Criteria

- [x] AC-01: `POST /api/v1/sessions` returns 201 with valid UUID `session_id` and empty history/metadata.
- [x] AC-02: Two session creates return distinct IDs.
- [x] AC-03: `ConversationHistory` keeps system prompt first after any number of trims.
- [x] AC-04: When `max_turns` exceeded, oldest user/assistant pair is removed; newer pairs remain.
- [x] AC-05: `POST /api/v1/sessions/{id}/estimate` returns success for valid session using **real** estimation path (mocked LLM in tests).
- [x] AC-06: After estimate, session history contains new user and assistant messages.
- [x] AC-07: Metadata block appears in composed system prompt (assert via mock/spy on render function).
- [x] AC-08: After forced history trim, `project_metadata` fields set earlier remain on session.
- [x] AC-09: Extractor validates LLM output with Pydantic; invalid output handled per FR-03 (tested).
- [x] AC-10: No-op turn preserves prior metadata scalars and lists.
- [x] AC-11: New list items append without duplication.
- [x] AC-12: Explicit user revision/removal updates or clears stale facts (tested).
- [x] AC-13: `uv run pytest` full suite passes; `uv run pytest --collect-only` has zero errors.
- [x] AC-14: No secrets in code, tests, or docs.

## Test Plan

### Unit

- `tests/test_sessions.py` — new metadata fields, `updated_at`, render helper if kept at domain layer.
- `tests/test_metadata_extractor.py` — merge preserve/append/revise/remove; mock `complete_structured`.

### Integration

- `tests/test_sessions_router.py` — TestClient: create session, estimate, 404 unknown session, history growth, metadata injection spy.

### Regression

- `uv run pytest` (full suite) after registering router in `main.py`.

### Manual

```bash
uv run uvicorn app.main:app --reload
curl -s -X POST http://localhost:8000/api/v1/sessions | jq
curl -s -X POST http://localhost:8000/api/v1/sessions/<id>/estimate \
  -H 'Content-Type: application/json' \
  -d '{"user_message": "Estimate a Python FastAPI CRUD, team of 3"}' | jq
```

## Verification

- **Automated:** `uv run pytest tests/test_sessions.py tests/test_metadata_extractor.py tests/test_sessions_router.py -v` — **Verified** (2026-05-18).
- **Automated (regression):** `uv run pytest` — **Verified** (265 passed, 2026-05-18).
- **Import gate:** `uv run python -c "from app.main import app"` — **Verified** (2026-05-18).
- **Manual:** curl flow above — **Not verified** (requires live server + API key).
- **Not verified:** multi-worker memory, persistence migration, production cost of extra LLM call per turn

## Documentation Plan

- `README.md`: document `/api/v1/sessions` and `/api/v1/sessions/{id}/estimate`.
- `app/main.py` `read_root()` keys for discoverability.
- Docstrings on store (volatility) and extractor (LLM strategy).
- This work item: update `## Implementation progress` and `## Repository commits` during `/start-task` / `/finish-task`.

## Implementation Plan

Recommended baby steps for `/start-task` (TDD each logic step):

- [ ] Step 1: Extend `ProjectMetadata` + `Session.updated_at` + tests (RED → GREEN).
- [ ] Step 2: `render_session_system_prompt` / Jinja integration + tests (metadata injection, no None placeholders).
- [ ] Step 3: `metadata_extractor` with `complete_structured` mock + merge tests (preserve/append/revise/remove).
- [ ] Step 4: `conversational_estimation_service` orchestration + unit tests (mock estimation + extractor).
- [ ] Step 5: `routers/sessions.py` + `test_sessions_router.py`; verify `--collect-only` clean.
- [ ] Step 6: Register router in `main.py`, README, full `pytest`, sync AC checkboxes.

## Estimation

- Size: M
- Estimated time: 3–4 hours
- Planned steps: 6

## Implementation progress

- [x] Step 1: Extend `ProjectMetadata` + `Session.updated_at` + tests (RED → GREEN)
- [x] Step 2: `render_session_system_prompt` + tests (metadata injection, no None placeholders)
- [x] Step 3: `metadata_extractor` with `complete_structured` mock + merge tests
- [x] Step 4: `conversational_estimation_service` orchestration + unit tests
- [x] Step 5: `routers/sessions.py` + `test_sessions_router.py`; `--collect-only` clean
- [x] Step 6: Register router in `main.py`, README, full `pytest`, sync AC checkboxes

## Pull Request

- https://github.com/povedica/master-ia-lidr/pull/15 — WIP draft (2026-05-18)

## Architecture Decision — Why LLM Extractor Over Heuristic Extraction

**1. Why history and project_metadata must be separate**

History is raw, append-only, and lossy (sliding window). Metadata is distilled, slowly growing, and queryable. One blob would make prompts grow O(n) with conversation length and lose facts when old turns are dropped.

**2. Why sliding window is enough for history**

Estimation sessions rarely need more than the last ~10 turns once scope stabilizes. `max_turns=10` bounds tokens and cost. Deeper recall can be added later (summary layer, RAG) without changing the `Session` aggregate.

**3. Why metadata surviving truncation helps**

- **Coherence:** model always sees agreed facts.
- **Cost:** small structured block vs full transcript.
- **Auditability:** log metadata snapshot per turn.

**4. Why LLM extractor vs heuristics**

Free-form and bilingual input breaks regex ("ya no usamos React", "team 4–5"). LLM extractor maps intent to `ProjectMetadata` reliably.

**5. Trade-offs**

- +1 LLM call per turn (cost, ~300–800 ms latency).
- Hallucination / missed revision risk → Pydantic validation, explicit merge tests, narrow prompt, low temperature.

**6. Why in-memory is acceptable now**

Domain types are persistence-agnostic. Swapping `InMemorySessionStore` for Redis/Postgres should not change routers, extractor, or prompt code.

## Learnings

- `/write-feature` must **never** ship application code; ambiguous prompts that say "implement" still mean **spec only** unless the user runs `/start-task` on the work item path.
- Verify `complete_structured` exists before any import from `structured_llm_client`.
- Run `uv run pytest --collect-only` before merging router registration.
- Avoid route-level stubs; orchestration service + existing `EstimationService` keeps boundaries clean.

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
| `eff5b99` | `docs(feature-018): add conversational memory work item and start-task plan` | Canonical work item + estimation/plan. |
| `c317278` | `feat(feature-018): extend ProjectMetadata and Session.updated_at` | Domain fields + unit tests. |
| `4480541` | `feat(feature-018): add render_session_system_prompt for metadata injection` | Jinja partial + prompt rendering tests. |
| `8b618c8` | `feat(feature-018): add metadata extractor with merge rules` | LLM extraction + merge unit tests. |
| `25b7ba4` | `feat(feature-018): add conversational estimation orchestration service` | Turn orchestration + service tests. |
| `d457ca2` | `feat(feature-018): add sessions router and integration tests` | HTTP routes without main registration. |
| `2b64631` | `feat(feature-018): register sessions routes and document API` | main.py, README, AC-08 test, full regression. |
| `TBD` | `docs(feature-018): add finish-task learnings and LLM extractor rationale` | Architecture decision table + implementation retrospective. |
