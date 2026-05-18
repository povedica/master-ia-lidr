# Feature: Conversational Session State — In-Memory Foundation

## Objective

Introduce a dedicated `app/services/sessions.py` module that models the internal session state
needed to evolve the estimator from a stateless transactional service towards a conversational one.

The goal of this step is the **domain model only**: no new HTTP endpoints, no metadata extraction,
no persistence. Future turns will build the multi-turn API on top of this foundation.

## Context

The current service is fully transactional: a single `EstimationRequest` in → estimation out.
Messages toward the LLM are constructed as plain `dict` literals (`{"role": ..., "content": ...}`)
inside `ai_model_service.py` and `structured_llm_client.py`. There is no shared message type and
no notion of conversation history or session identity beyond telemetry trace IDs.

The exercise explicitly requires a new `sessions.py` module with:
- `ConversationHistory`: bounded sliding-window message list that always preserves the system prompt.
- `ProjectMetadata`: Pydantic model capturing facts extracted during the conversation.
- `Session`: aggregate combining both of the above.
- `InMemorySessionStore`: encapsulated in-process dictionary keyed by `session_id`.

## Scope

### Includes
- `app/services/sessions.py` — full domain model.
- `tests/test_sessions.py` — focused unit tests for session-state behavior.

### Excludes
- `POST /sessions` endpoint.
- `POST /sessions/{session_id}/estimate` endpoint.
- Metadata extraction from LLM responses.
- Attachment handling in session context.
- Persistence (database, Redis, file system).
- Any change to existing routers, schemas, or services.

## Functional Requirements

1. `ChatMessage` — lightweight value type with `role` (`"system"` | `"user"` | `"assistant"`)
   and `content: str`.
2. `ConversationHistory` — stores messages in insertion order; keeps the system prompt as an
   immutable first slot; supports `set_system_prompt`, `add_user_message`, `add_assistant_message`,
   and `to_messages_list()`; when the number of non-system turns exceeds `max_turns`, removes the
   **oldest** user+assistant pair.
3. `ProjectMetadata` — Pydantic `BaseModel` with all fields optional and safe defaults; captures
   `project_name`, `assumed_team_size`, `mentioned_technologies`, and `agreed_scope`.
4. `Session` — dataclass with `session_id: str`, `created_at: datetime`, `conversation_history`,
   and `project_metadata`.
5. `InMemorySessionStore` — encapsulates a `dict[str, Session]`; exposes `create_session()`,
   `get_session()`, `exists()`, and `delete_session()`; no global mutable state leaked outside the
   class.

## Technical Approach

- **`ChatMessage`**: frozen dataclass (pure value, no methods beyond data access).
- **`ConversationHistory`**: regular class with a `_system: ChatMessage | None` slot and a
  `_turns: list[ChatMessage]` for non-system messages; sliding-window enforcement happens in
  `_enforce_window()` after each addition.
- **`ProjectMetadata`**: `pydantic.BaseModel` with `model_config = ConfigDict(frozen=False)` to
  allow partial updates as the conversation progresses.
- **`Session`**: `dataclass` (mutable aggregate; Pydantic is unnecessary here since the class
  contains non-Pydantic fields).
- **`InMemorySessionStore`**: plain class; `uuid.uuid4()` generates session IDs; module-level
  singleton exported as `session_store` for use by future routers.
- `to_messages_list()` returns `list[dict[str, str]]` — the same format already consumed by
  `ai_model_service.py` — avoiding any breaking change to the provider layer.

## Acceptance Criteria

- [x] AC-01: `sessions.py` exists under `app/services/` and imports cleanly.
- [x] AC-02: `ConversationHistory.to_messages_list()` returns `[{"role":"system","content":...}, ...]` when a system prompt is set.
- [x] AC-03: After exceeding `max_turns`, the system prompt is always the first message.
- [x] AC-04: After exceeding `max_turns`, the oldest user+assistant pair is removed.
- [x] AC-05: `ProjectMetadata` has all fields optional with sensible defaults.
- [x] AC-06: `Session` initializes with an empty `ConversationHistory` and a default `ProjectMetadata`.
- [x] AC-07: `InMemorySessionStore.create_session()` returns a `Session` and stores it internally.
- [x] AC-08: `InMemorySessionStore.get_session(id)` returns `None` for unknown IDs.
- [x] AC-09: `InMemorySessionStore.delete_session(id)` removes the session silently if absent.
- [x] AC-10: No import of `sessions.py` breaks any existing module.

## Test Plan

- **Unit tests** (all in `tests/test_sessions.py`):
  1. `ConversationHistory` preserves system prompt when window is exceeded.
  2. `ConversationHistory` drops oldest turns once `max_turns` is exceeded.
  3. `Session` creation initializes with empty/default `ProjectMetadata`.
  4. `InMemorySessionStore` stores and retrieves sessions by `session_id`.
  5. `InMemorySessionStore.get_session` returns `None` for unknown IDs.
  6. `InMemorySessionStore.delete_session` is idempotent.
- **Manual**: `python -c "from app.services.sessions import session_store; s = session_store.create_session(); print(s.session_id)"` should succeed.

## Verification

- **Automated**: `uv run pytest tests/test_sessions.py -v` — **Verified** (9 passed, 2026-05-18).
- **Automated (regression)**: `uv run pytest` — **Verified** (248 passed, 2026-05-18).
- **Manual**: `uv run python -c "from app.services.sessions import session_store; ..."` — **Verified**.
- **Not verified**: integration with future `/sessions` router.

## Documentation Plan

- Short docstrings in `sessions.py` explaining the in-memory tradeoff.
- No README update required at this stage (no new env vars, no new routes).

## Estimation

- Size: S
- Estimated time: 1.5 hours
- Planned steps: 4

## Implementation progress

- [x] Step 1: `ProjectMetadata` + `ChatMessage` (TDD)
- [x] Step 2: `ConversationHistory` sliding window (TDD)
- [x] Step 3: `Session` + `InMemorySessionStore` + `session_store` (TDD)
- [x] Step 4: Full verification + acceptance criteria sync

## Pull Request

- https://github.com/povedica/master-ia-lidr/pull/14 — merged into `main` via `/finish-task` (2026-05-18).

## Learnings

- Sliding-window history is simplest when `_turns` stores only user/assistant messages and `_enforce_window()` drops pairs (`len(_turns) // 2 > max_turns`).
- `to_messages_list()` returning `list[dict[str, str]]` keeps the future router integration aligned with `ai_model_service.py` without touching the provider layer yet.
- Module-level `session_store` is acceptable for the exercise; production would need Redis or similar (explicitly out of scope).

## Implementation Plan

> Superseded by baby-steps plan in `/start-task` (TDD order). See **Implementation progress** above.

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
| `60c2f74` | `docs(feature-017): add conversational session state work item spec` | Initial implementation-ready feature spec for in-memory session domain model (`sessions.py`, sliding window, store). |
| `3b1ea42` | `docs(feature-017): add repository commits table to work item` | Added `## Repository commits (master-ia)` section to the work item. |
| `5bc4d5f` | `docs(feature-017): add start-task estimation and implementation progress` | Added Estimation, Implementation progress, and Draft PR placeholders for `/start-task`. |
| `48920aa` | `docs(feature-017): record start-task setup commit in repository log` | Logged the start-task setup commit in the work item table. |
| `ae62471` | `docs(feature-017): link draft PR and mark acceptance verified` | PR #14 URL; verification and AC checkboxes updated. |
| `0c5d52b` | `feat(feature-017): add in-memory conversational session domain model` | `sessions.py`, `tests/test_sessions.py`, and `session_store` singleton. |
| `0703da3` | `docs(feature-017): record implementation commits in repository log` | Final commit table sync before merge. |
