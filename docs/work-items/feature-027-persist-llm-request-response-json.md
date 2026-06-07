# Feature: Persist LLM Request and Response as JSON

## Objective

Persist every outbound LLM call to the filesystem as a single JSON document containing the fully prepared request (immediately before the provider call) and the model response, controlled by an environment variable.

This extends the local debugging story started in [`feature-004-save-estimation-response-output.md`](feature-004-save-estimation-response-output.md), which persists only the final estimation text at the HTTP layer. Feature 027 captures **all** LLM traffic at the provider gateway, independent of endpoint or success path.

## Context

**Previous version (feature-004):**

- Toggle: `ESTIMATION_OUTPUT_PERSIST_ENABLED`
- Scope: `POST /api/v1/estimate` successful `200` responses only
- Format: markdown file with the `estimation` string
- Location: `output-responses/response-YYYYmmdd-hhmmss.md`

**This extension:**

- Toggle: `LLM_CALL_PERSIST_ENABLED` (new, default `false`)
- Scope: every LLM invocation through the centralized gateways
- Format: JSON with `{ "request": ..., "response": ... }`
- Location: same repo-root directory `output-responses/` (existing convention; already gitignored)
- Does **not** replace feature-004; both toggles can coexist. Feature-004 remains the API-level estimation export; feature-027 is the low-level LLM audit trail.

**Call sites to cover (all paths that reach LiteLLM):**

| Gateway | Module | Used by |
|---------|--------|---------|
| Chat completion | `app/services/ai_model_service.py` → `acomplete_chat` | `llm_chain.LitellmChainProvider.complete`, estimation, sessions |
| Streaming chat | `app/services/ai_model_service.py` → `astream_chat` | SSE streaming routes |
| Structured output | `app/services/structured_llm_client.py` → `complete_structured` | Domain guardrail extraction, metadata extractor, v2 structured estimation |

**Security:** never write API keys, tokens, or other secrets into persisted JSON. Redact `api_key` from any kwargs snapshot.

## Scope

### Includes

- Add `LLM_CALL_PERSIST_ENABLED` boolean setting (default `false`).
- When enabled, write one JSON file per completed LLM call to `output-responses/`.
- Filename pattern: `llm-call-YYYYmmdd-HHMMSS-<sequence>.json` (UTC; sequence avoids collisions within the same second).
- JSON document shape:

```json
{
  "recorded_at_utc": "2026-06-07T12:34:56.789Z",
  "call_kind": "chat",
  "preparation": {
    "api_endpoint": {"method": "POST", "path": "/api/v1/sessions/{id}/estimate"},
    "request_id": "sess_abc123",
    "templates": {
      "prompt_version": "estimation/v2",
      "examples_version": "file-flat-v4",
      "manifest": { "system_template": "estimation/v2/system.j2", "...": "..." },
      "rendered_template_names": ["examples.j2", "system.j2", "user.j2"]
    },
    "variables_before_render": { "detail_level": "medium", "output_format": "phases_table", "...": "..." },
    "prompt_overrides": { "messages_override": true, "messages_override_count": 3 },
    "notes": ["simplified_session_submit"]
  },
  "model_request": {
    "litellm_model": "openai/gpt-4o-mini",
    "chain_provider": "openai",
    "messages": [...],
    "max_output_tokens": 2048,
    "timeout_seconds": 30.0,
    "stream": false,
    "extra_kwargs": {}
  },
  "response": {
    "text": "...",
    "resolved_model": "gpt-4o-mini",
    "finish_reason": "stop",
    "usage": { "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150 }
  }
}
```

- **`preparation`**: everything before the provider call (HTTP route, Jinja context, templates, overrides).
- **`model_request`**: exact payload sent to LiteLLM/Instructor (no secrets).
- **`response`**: normalized provider outcome.
  - `chat`: `LiteLLMChatOutcome` fields
  - `stream`: aggregated text, usage if present, finish reason
  - `structured`: validated model as JSON (`model_dump()`), plus raw finish reason and usage when available
- Persist on **successful** provider calls only (model returned content or validated structured output).
- On provider failure, do **not** write a file (avoid partial/misleading dumps); log persistence errors without affecting API behavior.
- Persistence failures must **not** break estimation or session flows (best-effort, structured warning log).
- Unit tests for the writer helper and gateway hooks (mocked filesystem).
- Update `.env.example`, `README.md`, and `docs/technical/README.md`.

### Excludes

- Changing feature-004 behavior or removing `ESTIMATION_OUTPUT_PERSIST_ENABLED`.
- Persisting failed/provider-error calls (can be a follow-up).
- Retention, rotation, or cleanup policies.
- Streaming per-chunk files (one file per stream after aggregation).
- Langfuse/OTEL changes.
- Persisting guardrail-only deterministic checks (non-LLM).

## Functional Requirements

### FR-01: Environment toggle

- `LLM_CALL_PERSIST_ENABLED` (default `false`).
- When `false`, zero filesystem side effects from the new code paths.

### FR-02: Central persistence helper

- New module `app/services/llm_call_persistence.py` (or extend `response_output_writer.py` if kept small):
  - `build_llm_call_filename(now, sequence) -> str`
  - `persist_llm_call_record(payload: dict) -> Path`
  - Raises a domain-specific error on `OSError`; callers catch and log.

### FR-03: Chat completion hook (`acomplete_chat`)

- After building `messages` and `kwargs`, before `acompletion`, assemble the request snapshot.
- After successful normalization (`LiteLLMChatOutcome`), write JSON with request + response.
- Skip when toggle is off.

### FR-04: Streaming hook (`astream_chat`)

- Same request snapshot before opening the stream.
- After stream completes successfully, write one JSON file with aggregated text and usage.

### FR-05: Structured hook (`complete_structured`)

- Request snapshot from `completion_messages` and call parameters.
- On successful validation, response includes `structured_output` (Pydantic JSON) and usage/finish metadata.
- Each **successful** attempt writes one file; failed validation retries do not write until success.

### FR-06: Secret safety

- Never persist `api_key` or values from env secrets.
- `extra_kwargs` in the request block lists only safe keys (`timeout`, `stream`, `stream_options`, `max_completion_tokens` / `max_tokens` as applicable).

### FR-07: Failure isolation

- Persistence errors are logged with stable keys (`llm_call_persist_failed`) and do not alter provider error handling or HTTP responses.

## Technical Approach

### Settings (`app/config.py`)

```python
llm_call_persist_enabled: bool = False
```

### Helper (`app/services/llm_call_persistence.py`)

- Reuse repo-root resolution pattern from `response_output_writer.py`.
- Output directory: `_REPO_ROOT / "output-responses"`.
- Serialize with `json.dumps(..., ensure_ascii=False, indent=2)`.
- In-process monotonic sequence counter (or microsecond suffix) for filename uniqueness.

### Gateway integration

1. **`ai_model_service.py`**: inject settings via optional parameter or lazy `get_settings()` to avoid circular imports; prefer passing `persist_enabled: bool` from callers if cleaner — default: read settings inside helper at write time.
2. **`structured_llm_client.py`**: call the same helper after successful parse.

### Relationship to feature-004

| Toggle | Layer | Content |
|--------|-------|---------|
| `ESTIMATION_OUTPUT_PERSIST_ENABLED` | Router | Final estimation markdown for HTTP 200 |
| `LLM_CALL_PERSIST_ENABLED` | LLM gateway | Full request/response JSON per provider call |

## Acceptance Criteria

- [x] AC-01: `LLM_CALL_PERSIST_ENABLED=false` produces no new files and no behavior change.
- [x] AC-02: When enabled, each successful `acomplete_chat` call writes one JSON file under `output-responses/`.
- [x] AC-03: When enabled, each successful `astream_chat` call writes one aggregated JSON file.
- [x] AC-04: When enabled, each successful `complete_structured` call writes one JSON file with structured output.
- [x] AC-05: JSON files contain complete `request.messages` and normalized `response` without API keys.
- [x] AC-06: Persistence failure does not fail user-facing requests.
- [x] AC-07: `.env.example` and README document the new variable.
- [x] AC-08: `uv run pytest` passes without real API keys.

## Test Plan

### Unit tests

- `tests/test_llm_call_persistence.py`: filename format, JSON shape, directory creation, error mapping.
- Extend `tests/test_ai_model_service.py`: with toggle on (monkeypatch helper), verify persist called after success; off → not called.
- Extend `tests/test_structured_llm_client.py`: persist on successful structured completion.

### Manual checks

- Set `LLM_CALL_PERSIST_ENABLED=true`, run one estimate request, confirm JSON files appear in `output-responses/` with expected request/response bodies.

## Documentation Plan

- `.env.example`: add `LLM_CALL_PERSIST_ENABLED=false` with comment.
- `README.md` and `docs/technical/README.md`: env table row and directory note.

## Implementation Plan

- [ ] Step 1: Add setting + persistence helper + unit tests (RED → GREEN).
- [ ] Step 2: Wire `acomplete_chat` hook + tests.
- [ ] Step 3: Wire `astream_chat` hook + tests.
- [ ] Step 4: Wire `complete_structured` hook + tests.
- [ ] Step 5: Sync docs and `.env.example`.

## Implementation progress

- [x] Step 1: Setting + helper + unit tests
- [x] Step 2: `acomplete_chat` hook
- [x] Step 3: `astream_chat` hook
- [x] Step 4: `complete_structured` hook
- [x] Step 5: Documentation sync

## Verification

### Automated

- `uv run pytest tests/test_llm_call_persistence.py tests/test_ai_model_service.py tests/test_structured_llm_client.py tests/test_config.py::test_llm_call_persist_can_be_enabled_from_env` — 24 passed.

### Manual

- Not verified: live estimate with `LLM_CALL_PERSIST_ENABLED=true` and inspection of JSON files.

### Residual risk

- Concurrent calls in the same second rely on an in-process sequence counter (sufficient for local debugging).

## Open questions

- None for v1; failed-call persistence deferred intentionally.

## Estimation

- Size: S
- Estimated time: 1–2 hours
- Planned steps: 5
