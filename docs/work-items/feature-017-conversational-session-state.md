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

- [ ] AC-01: `sessions.py` exists under `app/services/` and imports cleanly.
- [ ] AC-02: `ConversationHistory.to_messages_list()` returns `[{"role":"system","content":...}, ...]` when a system prompt is set.
- [ ] AC-03: After exceeding `max_turns`, the system prompt is always the first message.
- [ ] AC-04: After exceeding `max_turns`, the oldest user+assistant pair is removed.
- [ ] AC-05: `ProjectMetadata` has all fields optional with sensible defaults.
- [ ] AC-06: `Session` initializes with an empty `ConversationHistory` and a default `ProjectMetadata`.
- [ ] AC-07: `InMemorySessionStore.create_session()` returns a `Session` and stores it internally.
- [ ] AC-08: `InMemorySessionStore.get_session(id)` returns `None` for unknown IDs.
- [ ] AC-09: `InMemorySessionStore.delete_session(id)` removes the session silently if absent.
- [ ] AC-10: No import of `sessions.py` breaks any existing module.

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

- **Automated**: `uv run pytest tests/test_sessions.py -v`
- **Manual**: import smoke-test above.
- **Not verified yet**: integration with future `/sessions` router.

## Documentation Plan

- Short docstrings in `sessions.py` explaining the in-memory tradeoff.
- No README update required at this stage (no new env vars, no new routes).

## Implementation Plan

- [ ] Step 1: Write `app/services/sessions.py` with `ChatMessage`, `ConversationHistory`, `ProjectMetadata`, `Session`, `InMemorySessionStore`, and `session_store` singleton.
- [ ] Step 2: Write `tests/test_sessions.py` covering the six unit tests above.
- [ ] Step 3: Run `uv run pytest tests/test_sessions.py -v` and confirm green.
