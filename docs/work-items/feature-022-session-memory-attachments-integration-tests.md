# Feature: Integration Test Suite — Session Memory, Metadata, and Attachments

## 1) Problem statement

The estimator backend now supports **multi-turn session state**: in-memory sessions, sliding-window conversation history, distilled `project_metadata`, and attachment-aware estimation via `POST /api/v1/sessions` and `POST /api/v1/sessions/{session_id}/estimate`.

Existing tests cover **isolated units** (`tests/test_sessions.py`, `tests/test_conversational_estimation_service.py`, `tests/test_metadata_extractor.py`) and **thin router tests** that mock `SimplifiedSessionEstimationService` entirely (`tests/test_simplified_session_router.py`, `tests/test_sessions_router.py`). Those router tests validate HTTP status codes and response envelopes but **do not exercise**:

- Real orchestration through `SimplifiedSessionEstimationService` (or `ConversationalEstimationService`).
- Progressive enrichment and re-injection of `project_metadata` across linked submits.
- Attachment extraction → prompt composition → observable LLM input.
- Sliding-window trimming under repeated submits within one `session_id`.
- Session isolation between concurrent sessions.

Without a focused integration suite, regressions in prompt composition, metadata persistence, attachment context, or history trimming can ship while unit and mocked-router tests remain green.

## 2) Goals and non-goals

### Goals

- Add a **minimal but robust** pytest integration suite using **`httpx.AsyncClient`** against the real FastAPI app.
- Exercise the **full in-process path**: routing → Pydantic validation → session store → orchestration → prompt rendering → (faked) LLM call → response assembly.
- Provide an **inspectable LLM fake** that captures prompts/messages and returns deterministic structured outputs.
- Cover the four **mandatory scenarios** (session creation, two linked turns, attachment influence, sliding window).
- Keep tests **fast**, **deterministic**, and **free of real provider/network calls**.
- Document in README how to run the suite and which attachment strategy the project uses.

### Non-goals

- Persistence across process restarts (in-memory store is sufficient).
- Complex memory compression (anchors, hybrid tiers, dynamic summarization).
- Real OpenAI/Anthropic/LiteLLM network calls or real Files API uploads.
- End-to-end browser/UI tests (`front-feature-021` scope).
- Replacing all existing unit tests or router smoke tests.
- Performance/load testing of the session store.
- Testing exact natural-language phrasing of LLM outputs (prefer structural/marker-based assertions).

## 3) Functional scope of the tests

### Full integration (real code under test)

| Layer | What is exercised |
| --- | --- |
| HTTP routing | `app/routers/sessions.py` — `POST /api/v1/sessions`, `POST /api/v1/sessions/{session_id}/estimate` |
| Request validation | `SessionEstimateRequest`, `AttachmentRef` (`app/schemas/simplified_session.py`) |
| Session lifecycle | `InMemorySessionStore`, `Session`, `ConversationHistory`, `ProjectMetadata` (`app/services/sessions.py`) |
| Orchestration | `SimplifiedSessionEstimationService.run_submit()` (`app/services/simplified_session_estimation_service.py`) |
| Metadata derivation | `derive_project_metadata()` (`app/services/simplified_session_metadata.py`) — heuristic path used by simplified submits |
| Attachment pipeline | `process_attachment_refs()` → `DocumentTextExtractor` → `DynamicContextManager.build_context_block()` |
| Prompt composition | `render_session_system_prompt()`, `render_guided_user_message()`, `_compose_user_prompt()` |
| Guarded pipeline wiring | `LLMPipeline.run_structured()` up to the provider/structured-client boundary |
| Response assembly | `assemble_estimation_v2_response()`, `SessionEstimateResponse` envelope |

### Replaced by test doubles

| Dependency | Why mocked/faked |
| --- | --- |
| `complete_structured()` / LiteLLM provider chain | Avoid network; return deterministic `EstimationResult` |
| OpenAI/Anthropic Files API (Path A) | No real upload; fake returns synthetic `file_id` references |
| Heavy PDF/DOCX parsing (optional) | Default: use **minimal real extractors** on tiny fixtures (< 5 KB); optionally stub `DocumentTextExtractor.extract_one` only when building corrupt-file edge-case tests |
| Semantic cache Redis | Disabled via settings (`semantic_cache_enabled=false`) or noop backend |
| Langfuse / OTEL export | Already noop via `tests/conftest.py` autouse fixture |
| Metadata LLM extractor (`extract_and_merge_metadata`) | **Not on the simplified submit hot path**; if conversational route is wired later, fake at `complete_structured` boundary |

### Boundary note (current vs exercise ideal)

The codebase today uses:

- **Simplified JSON submit** (`SessionEstimateRequest`) with **base64 inline attachments** (`AttachmentRef.content_base64`), not `multipart/form-data`.
- **Path B (local text extraction)** via `pypdf` / `python-docx` (`app/services/document_extractor.py`).
- **Heuristic metadata derivation** on submit, not the LLM extractor in `metadata_extractor.py` (that serves `ConversationalEstimationService`).

The exercise also describes **multipart/form-data** and **Path A (provider Files API)**. This spec requires tests to be **adaptable** to both transport and attachment paths; the implementation must pick one transport for production, document it, and map Test 3 accordingly (see §5.3 and §7).

## 4) Technical test design

### 4.1 Application harness

Use the **real app factory** from `app.main:app` (or a thin `tests/support/app_factory.py` wrapper) with dependency overrides for test-only concerns:

```python
# tests/support/app_factory.py (sketch)
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.config import Settings, get_settings
from app.services.sessions import InMemorySessionStore, session_store

def test_settings() -> Settings:
    return Settings(
        openai_api_key="test-key",
        llm_domain_guardrail_enabled=False,
        semantic_cache_enabled=False,
        max_attachment_context_chars=8_000,
    )

async def async_client(store: InMemorySessionStore, fake_llm: FakeStructuredLLM) -> AsyncClient:
    app.dependency_overrides[get_settings] = lambda: test_settings()
    # Wire fake into EstimationService provider chain — see §4.3
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")
```

Prefer **`httpx.AsyncClient` + `ASGITransport`** over sync `TestClient` for this suite (exercise requirement). Mark tests `@pytest.mark.asyncio`.

### 4.2 Session state access

**Primary approach:** inject a **test-scoped `InMemorySessionStore`** and patch module references so router and service share the same instance.

Add a small test helper on the store (implementation step):

```python
# app/services/sessions.py — test-only helper
class InMemorySessionStore:
    ...
    def reset_for_tests(self) -> None:
        """Clear all sessions; use only from pytest fixtures."""
        self._sessions.clear()
```

**Test access pattern:**

```python
# tests/fixtures/session_store.py
def get_session_state(store: InMemorySessionStore, session_id: str) -> Session:
    session = store.get_session(session_id)
    assert session is not None
    return session
```

Patch targets (all must reference the same store instance):

- `app.services.sessions.session_store`
- `app.routers.sessions.session_store`
- Store passed into `SimplifiedSessionEstimationService` via `get_simplified_session_service` override **or** shared singleton patch.

Do **not** add a production debug endpoint for session introspection.

### 4.3 Inspectable LLM fake

Introduce `tests/fakes/fake_llm_provider.py` (and optionally `tests/fakes/fake_structured_llm.py`) that records every structured completion call.

**Capture contract:**

```python
@dataclass
class CapturedLLMCall:
    system_prompt: str
    user_prompt: str
    messages: list[dict[str, str]] | None  # populated when orchestration passes history
    response_model: type
    call_index: int

class FakeStructuredLLM:
    calls: list[CapturedLLMCall]

    async def complete_structured(self, *, system_prompt, user_prompt, response_model, **kwargs):
        self.calls.append(CapturedLLMCall(...))
        return self._dispatch(system_prompt, user_prompt, response_model)
```

**Injection point (preferred):** monkeypatch `app.services.structured_llm_client.complete_structured` to delegate to `FakeStructuredLLM`. This keeps `LLMPipeline`, guardrails, and `EstimationService.estimate_structured` real while eliminating network I/O.

**Deterministic dispatch rules** (marker-driven, no NL parsing):

| Marker in `user_prompt` or `transcript` | Fake returns |
| --- | --- |
| `[[TECH:redis]]` | `EstimationResult` line item named `"Redis integration"` |
| `[[TEAM:5]]` | Metadata side-effect: tests assert `project_name` / team via **heuristic derivation** from request fields, not fake |
| `ATTACH_MARKER:USE_REDIS` (inside attachment text) | `EstimationResult` includes `"Redis (from attachment)"` in summary or a dedicated line item |
| Default | Minimal valid `EstimationResult` fixture (1 line item, totals, confidence) |

For metadata enrichment assertions, rely on **`derive_project_metadata()`** (deterministic from explicit form fields + transcript keywords), not on the fake LLM inventing metadata.

**Assistant turn simulation:** after a successful structured call, orchestration appends a compact assistant message to `ConversationHistory` via `_compact_estimation_summary()`. The fake must return a result whose `title`/`summary` are stable strings (e.g. `"Estimate"`, `"Fixed summary for turn N"`) so history assertions do not depend on model creativity.

### 4.4 ConversationHistory inspection

Tests assert on **two complementary views**:

1. **Session store (ground truth for memory):** `session.conversation_history.to_messages_list()` after each HTTP call.
2. **LLM fake (ground truth for provider input):** latest `CapturedLLMCall.system_prompt` and `.user_prompt` (and `.messages` when wired).

**System prompt metadata injection:** assert substring markers from `render_session_system_prompt()` — e.g. project name appears in the metadata block Jinja partial (`estimation/v2/partials/session_project_metadata.md.j2`), not as `project_name: None`.

### 4.5 Sliding window test configuration

Default production `max_turns=10`. For Test 4, **lower the window in test setup** to avoid eight slow HTTP round-trips:

```python
@pytest.fixture
def narrow_window_store() -> InMemorySessionStore:
    store = InMemorySessionStore()
    # Option A: mutate default on create (if Session accepts max_turns param)
    # Option B: after create_session(), set session.conversation_history.max_turns = 3
    return store
```

With `max_turns=3`, **7 submits** force trimming (7 user+assistant pairs stored; window keeps last 3 pairs).

### 4.6 Attachment paths

| Path | Production behavior | Test assertion focus |
| --- | --- | --- |
| **B — Local extraction (current default)** | `DocumentTextExtractor` → `DynamicContextManager` → `_compose_user_prompt()` | Fake `user_prompt` contains `<attachments>` block with `<attachment filename="...">` and marker text |
| **A — Direct multimodal** | Upload via provider Files API; message content references `file_id` | Fake receives content parts array or provider-specific file reference; **no real upload** — fake Files adapter returns `"file-test-abc"` |

**Recommended default for testability:** Path B. Path A tests use a **`FakeFilesUploader`** injected at the attachment adapter boundary.

### 4.7 Transport: JSON base64 vs multipart

| Transport | When to use in tests |
| --- | --- |
| **JSON + base64** (current `SessionEstimateRequest`) | Default for Test 3 until multipart route exists |
| **multipart/form-data** | Add `tests/support/multipart_submit.py` helper; enable when router accepts `UploadFile` fields |

Test 3 must document both helpers; CI runs the one matching implemented transport.

## 5) Detailed test cases

Suggested module: **`tests/test_sessions_integration.py`**

Supporting modules:

- `tests/fixtures/session_store.py`
- `tests/fixtures/transcripts.py`
- `tests/fixtures/attachment_bytes.py`
- `tests/fakes/fake_llm_provider.py`
- `tests/support/app_factory.py`

---

### Test 1 — Session creation

**ID:** `test_create_session_initializes_empty_state`

**Endpoint:** `POST /api/v1/sessions`

**Flow:**

1. `POST /api/v1/sessions`
2. Read session from test store via `get_session_state(store, session_id)`

**Asserts:**

- HTTP **201 Created**
- Body `{"session_id": "<uuid>"}` — valid UUID v4 format
- `store.exists(session_id)` is true
- `session.conversation_history.to_messages_list() == []`
- `session.project_metadata == ProjectMetadata()` (all fields empty/default)
- `session.submit_count == 0`
- Two consecutive creates return **different** `session_id` values

**Example:**

```python
async def test_create_session_initializes_empty_state(async_client, session_store):
    r = await async_client.post("/api/v1/sessions")
    assert r.status_code == 201
    session_id = r.json()["session_id"]
    session = get_session_state(session_store, session_id)
    assert session.project_metadata.project_name is None
    assert session.conversation_history.to_messages_list() == []
```

---

### Test 2 — Two linked requests within the same session

**ID:** `test_two_linked_submits_enrich_metadata_and_inject_into_system_prompt`

**Endpoints:** `POST /api/v1/sessions`, then two calls to `POST /api/v1/sessions/{session_id}/estimate`

**Transcript fixtures** (`tests/fixtures/transcripts.py`):

```python
TURN_1 = {
    "project_name": "Acme Portal",
    "project_type": "web_saas",
    "target_audience": "b2b_smb",
    "transcript": (
        "We need a B2B SaaS customer portal for Acme Corp. "
        "Stack: Python, FastAPI, PostgreSQL. Team of 4 developers. "
        "Scope: authentication, dashboard, billing integration."
    ),  # ≥ 80 chars
}
TURN_2 = {
    **TURN_1,
    "transcript": (
        "Same Acme Portal project — add Redis caching for session tokens "
        "and keep the existing PostgreSQL datastore."
    ),
}
```

**Flow:**

1. Create session.
2. Submit Turn 1 JSON body.
3. Submit Turn 2 JSON body (same `session_id`).

**Asserts after Turn 1:**

- HTTP 200; response envelope contains `project_metadata.project_name == "Acme Portal"`
- `session.project_metadata.project_name == "Acme Portal"` (compact metadata on session)
- `session.conversation_history.to_messages_list()` length ≥ 3 (system + user + assistant)
- Latest fake call: `system_prompt` contains `"Acme Portal"` in metadata block
- Fake call `user_prompt` contains Turn 1 transcript content (or rendered guided message derived from it)

**Asserts after Turn 2:**

- Response `project_metadata.project_name` still `"Acme Portal"`
- Latest fake call: `system_prompt` includes metadata from Turn 1 (`"Acme Portal"`) **before** Turn 2 LLM invocation — proves re-injection
- `session.conversation_history.to_messages_list()`:
  - Index 0 role == `"system"`
  - Contains Turn 1 compact user label (`"[Simplified submit] Acme Portal"`) and assistant summary from Turn 1
  - Ends with Turn 2 user label + Turn 2 assistant summary
- **Sliding window consistency:** if `max_turns` not yet exceeded, fake or history includes Turn 1 context; when using future multi-message provider API, fake `.messages` mirrors `to_messages_list()`

**Explicit non-assertion:** do not assert exact Jinja whitespace; assert **presence of stable markers** (`Acme Portal`, `Redis`, role ordering).

---

### Test 3 — Request with attachment

**ID:** `test_attachment_text_influences_llm_prompt_and_estimate`

**Flow:**

1. Create session.
2. Submit estimate with transcript + one attachment containing unique marker `ATTACH_MARKER:USE_REDIS`.

**Attachment fixture** (`tests/fixtures/attachment_bytes.py`):

Minimal PDF (preferred) or DOCX built in-test with `pypdf` / `python-docx` **or** static bytes committed under `tests/fixtures/files/redis_scope.pdf` (< 3 KB):

```text
Project addendum: ATTACH_MARKER:USE_REDIS must be reflected in the estimate.
```

**Submit payload (JSON base64 — current API):**

```python
{
  "project_name": "Acme Portal",
  "project_type": "web_saas",
  "target_audience": "b2b_smb",
  "transcript": "See attached addendum for caching requirements. " * 4,
  "attachments": [{
    "file_id": "f1",
    "name": "redis_addendum.pdf",
    "mime_type": "application/pdf",
    "content_base64": "<bytes>"
  }]
}
```

**Asserts:**

- HTTP 200; `attachments[0].status == "processed"` in response
- `project_metadata.attachment_summary` mentions `redis_addendum.pdf` (or equivalent derived field)
- **Path B:** latest fake `user_prompt` contains:
  - `<attachments>` wrapper
  - `filename="redis_addendum.pdf"`
  - substring `ATTACH_MARKER:USE_REDIS`
- **Path A (if implemented):** fake captures file reference part (e.g. `{"type": "file", "file_id": "file-test-abc"}`) instead of extracted text
- **Output differentiation:** configure fake so when marker present, structured result includes line item `"Redis (from attachment)"`; assert `response.json()["estimate"]["result"]["line_items"]` contains that name
- **Control case:** same submit **without** attachment must **not** include `"Redis (from attachment)"` (second test or parametrized negative path: `test_attachment_missing_does_not_inject_marker`)

**Multipart variant (when implemented):**

```python
files = {"attachments": ("redis_addendum.pdf", pdf_bytes, "application/pdf")}
data = {"payload": json.dumps({...})}  # or discrete form fields
await async_client.post(url, data=data, files=files)
```

---

### Test 4 — Sliding window with more than MAX_TURNS

**ID:** `test_sliding_window_drops_oldest_pairs_preserves_system_prompt`

**Setup:** `session.conversation_history.max_turns = 3` (test-only configuration)

**Flow:**

1. Create session.
2. Loop **7 submits** with distinct markers in transcript: `TURN_MARKER:01` … `TURN_MARKER:07` (reuse minimal valid body; vary `one_line_summary` or append marker to transcript).

**Asserts after each submit (final submit matters most):**

- Latest fake/history messages: **at most** `1 + (max_turns * 2)` entries (system + N pairs)
- First message role always `"system"`; system content includes current metadata block
- **Oldest pairs dropped:** history does **not** contain user content with `TURN_MARKER:01` or `TURN_MARKER:02` after 7 turns with `max_turns=3`; **does** contain `TURN_MARKER:07`
- **`project_metadata` survives trim:** set `project_name` on Turn 1; after Turn 7, `session.project_metadata.project_name` still set
- Pair integrity: never orphan a user message without its assistant reply in stored history

**Helper assertion function:**

```python
def assert_window(messages: list[dict], *, max_turns: int) -> None:
    assert messages[0]["role"] == "system"
    non_system = messages[1:]
    assert len(non_system) <= max_turns * 2
    roles = [m["role"] for m in non_system]
    assert roles == ["user", "assistant"] * (len(non_system) // 2)
```

---

### Additional recommended tests (non-mandatory but high value)

| ID | Scenario | Expected |
| --- | --- | --- |
| `test_unknown_session_returns_404` | Estimate with random UUID | 404, store unchanged |
| `test_session_isolation` | Two sessions, enrich A only | B's metadata stays empty |
| `test_empty_attachment_base64_fails_gracefully` | Missing `content_base64` | 200 with attachment `status: failed` or 422 — match OpenAPI contract |
| `test_unsupported_mime_rejected` | `application/zip` | 422 with safe error |
| `test_fresh_session_does_not_leak_prior_metadata` | New session after enriching old | Empty metadata |

## 6) Fixtures, doubles and test utilities

### 6.1 Pytest fixtures (`tests/conftest.py` extensions or `tests/fixtures/conftest_sessions.py`)

| Fixture | Scope | Purpose |
| --- | --- | --- |
| `session_store` | function | Fresh `InMemorySessionStore`; calls `reset_for_tests()` teardown |
| `fake_structured_llm` | function | Clean `FakeStructuredLLM` with deterministic dispatch table |
| `async_client` | function | `httpx.AsyncClient` bound to app with overrides applied |
| `patch_session_store` | function (autouse for integration module) | Patches all `session_store` import sites to shared instance |
| `disable_semantic_cache` | function | Ensures `Settings.semantic_cache_enabled=False` |

```python
@pytest.fixture
def session_store() -> InMemorySessionStore:
    store = InMemorySessionStore()
    yield store
    store.reset_for_tests()

@pytest.fixture
async def async_client(session_store, fake_structured_llm, monkeypatch):
    patch_all_session_stores(monkeypatch, session_store)
    install_fake_structured_llm(monkeypatch, fake_structured_llm)
    async with await make_async_client() as client:
        yield client
```

### 6.2 Transcript builders (`tests/fixtures/transcripts.py`)

```python
def build_transcript(*, marker: str, min_len: int = 80) -> str:
    base = f"Project discussion marker={marker}. "
    return base * (min_len // len(base) + 1)

def simplified_submit_payload(**overrides) -> dict:
    defaults = {"project_name": "Test", "project_type": "web_saas", ...}
    return {**defaults, **overrides}
```

### 6.3 Attachment builders (`tests/fixtures/attachment_bytes.py`)

```python
def minimal_pdf_with_text(text: str) -> bytes: ...
def minimal_docx_with_text(text: str) -> bytes: ...
def attachment_ref(name: str, mime: str, raw: bytes) -> dict: ...
```

Use **real minimal documents** (not mocked bytes) for the happy path so `pypdf`/`python-docx` integration stays covered.

### 6.4 Fake LLM (`tests/fakes/fake_llm_provider.py`)

Must implement:

- `calls: list[CapturedLLMCall]`
- `last_call() -> CapturedLLMCall`
- `reset() -> None`
- Deterministic structured response factory using `tests/estimation_fixtures.py` patterns (`StructuredEstimateBundle` / `EstimationResult`)

Optional: `FakeFilesUploader` for Path A returning `UploadedFileRef(file_id="file-test-abc", filename=...)`.

### 6.5 Session helpers (`tests/fixtures/session_store.py`)

```python
def get_session_state(store: InMemorySessionStore, session_id: str) -> Session: ...
def messages_for_session(store, session_id) -> list[dict[str, str]]: ...
```

## 7) Risks and open questions

| Risk / question | Mitigation / decision |
| --- | --- |
| **Router mocks service today** — integration tests bypass real orchestration if override persists | Do **not** override `get_simplified_session_service` in this suite; only override settings + LLM boundary |
| **Provider boundary may not receive full `to_messages_list()`** (feature-018 follow-up) | Assert session history separately from fake `system_prompt`/`user_prompt`; add `.messages` assertion when multi-message wiring lands |
| **Heuristic vs LLM metadata** — simplified path uses `derive_project_metadata`, not `metadata_extractor` | Test 2 asserts heuristic fields (`project_name` from form, constraints from transcript keywords); document in README |
| **JSON vs multipart** — exercise mentions multipart; codebase uses JSON base64 | **Open question:** implement multipart in a follow-up feature, or add optional multipart route for parity. Test 3 ships with JSON; multipart helper stubbed |
| **Path A vs Path B** | **Open question for implementer:** confirm Path B as production default (recommended). Path A tests behind `pytest.mark.attachment_path_a` |
| **Guardrails may block marker transcripts** | Disable domain guardrails in test settings (`llm_domain_guardrail_enabled=False`) unless testing guardrail interaction |
| **Session store singleton leakage between tests** | Function-scoped store + autouse patch + `reset_for_tests()` |
| **Invalid session_id** | Cover 404 now (recommended test); malformed UUID format — document expected behavior (404 vs 422) |
| **Empty transcript** | Document as 422 validation error; optional test |
| **Unsupported/corrupt attachments** | Document; cover unsupported MIME in recommended tests; corrupt PDF as follow-up |
| **Flaky PDF text extraction** | Use simple single-page PDF fixtures; assert substring presence, not full extracted text equality |

## 8) Acceptance criteria

- [ ] **AC-01:** `tests/test_sessions_integration.py` exists with Test 1–4 implemented and passing via `uv run pytest tests/test_sessions_integration.py`.
- [ ] **AC-02:** Suite uses **`httpx.AsyncClient`** (async tests), not sync `TestClient`, for session integration tests.
- [ ] **AC-03:** No real external LLM or Files API calls during test runs (verified by monkeypatched `complete_structured` and absent network usage).
- [ ] **AC-04:** Test 1 verifies empty `ConversationHistory` and `ProjectMetadata` in the store after `POST /api/v1/sessions`.
- [ ] **AC-05:** Test 2 verifies metadata enrichment after Turn 1 and metadata presence in Turn 2 **system prompt** captured by fake.
- [ ] **AC-06:** Test 2 verifies `conversation_history.to_messages_list()` accumulates both turns with system prompt first.
- [ ] **AC-07:** Test 3 verifies attachment content reaches fake `user_prompt` (Path B) or file reference (Path A) and changes structured output deterministically.
- [ ] **AC-08:** Test 4 verifies at most `max_turns` user+assistant pairs in history, system prompt always present, oldest markers dropped.
- [ ] **AC-09:** Test 4 verifies `project_metadata` persists after history trim.
- [ ] **AC-10:** Session isolation verified (session B not affected by session A) — recommended test.
- [ ] **AC-11:** `InMemorySessionStore.reset_for_tests()` (or equivalent) prevents cross-test leakage.
- [ ] **AC-12:** `FakeStructuredLLM` exposes `calls` / `last_call()` for inspection.
- [ ] **AC-13:** Full suite runtime for integration module **< 10 seconds** on local dev machine (target; not a hard CI gate).
- [ ] **AC-14:** README updated: how to run tests, attachment path chosen, metadata derivation strategy (heuristic vs LLM).
- [ ] **AC-15:** No secrets in fixtures or committed attachment samples.

## 9) Step-by-step implementation plan

### Step 0 — Gate and baseline

- [ ] Confirm feature-020 session routes are stable on `main`.
- [ ] Run `uv run pytest tests/test_sessions.py tests/test_simplified_session_router.py --collect-only` — note existing coverage gaps.
- [ ] Record baseline pass count.

### Step 1 — Test infrastructure scaffolding

- [ ] Add `InMemorySessionStore.reset_for_tests()` in `app/services/sessions.py`.
- [ ] Create `tests/fakes/fake_llm_provider.py` with `CapturedLLMCall` and `FakeStructuredLLM`.
- [ ] Create `tests/support/app_factory.py` with async client factory.
- [ ] Create `tests/fixtures/session_store.py` helpers.
- [ ] Extend conftest or add `tests/fixtures/conftest_sessions.py` with `session_store`, `fake_structured_llm`, `async_client` fixtures.
- **Verify:** fake unit test — calling patched `complete_structured` appends to `calls` list.

### Step 2 — Test 1 (session creation)

- [ ] Implement `test_create_session_initializes_empty_state` in `tests/test_sessions_integration.py`.
- **Verify:** `uv run pytest tests/test_sessions_integration.py::test_create_session_initializes_empty_state -q`

### Step 3 — Test 2 (two linked submits)

- [ ] Add `tests/fixtures/transcripts.py` with Turn 1/2 payloads.
- [ ] Implement metadata + system prompt + history assertions.
- **Verify:** single test green; inspect fake `calls[0]` vs `calls[1]` manually on first failure.

### Step 4 — Attachment fixtures + Test 3

- [ ] Add `tests/fixtures/attachment_bytes.py` with minimal PDF/DOCX generators.
- [ ] Wire fake dispatch rule for `ATTACH_MARKER:USE_REDIS`.
- [ ] Implement positive + negative attachment tests.
- **Verify:** `uv run pytest tests/test_sessions_integration.py -k attachment -q`

### Step 5 — Test 4 (sliding window)

- [ ] Implement loop submit helper with turn markers.
- [ ] Set `max_turns=3` on session history after creation (before submits).
- [ ] Add `assert_window` helper.
- **Verify:** `uv run pytest tests/test_sessions_integration.py -k sliding -q`

### Step 6 — Recommended edge tests

- [ ] `test_unknown_session_returns_404`
- [ ] `test_session_isolation`
- **Verify:** full module green.

### Step 7 — Documentation and CI

- [ ] README: add **Integration tests (sessions)** section with `uv run pytest tests/test_sessions_integration.py`.
- [ ] Document attachment path (B recommended) and metadata derivation (heuristic for simplified submit).
- [ ] Optional: add integration module to CI workflow if not already running full `pytest`.
- **Verify:** `uv run pytest tests/test_sessions_integration.py` all green; `uv run pytest` full suite still green.

## Context (repository references)

| Artifact | Location |
| --- | --- |
| Session domain model | `app/services/sessions.py` |
| HTTP routes | `app/routers/sessions.py` |
| Simplified orchestration | `app/services/simplified_session_estimation_service.py` |
| Conversational orchestration (LLM metadata extractor) | `app/services/conversational_estimation_service.py` |
| Attachment processing | `app/services/simplified_attachment_processing.py`, `app/services/document_extractor.py` |
| Prompt metadata injection | `app/services/estimation_prompt_rendering.py` → `render_session_system_prompt()` |
| Structured LLM boundary | `app/services/structured_llm_client.py` → `complete_structured()` |
| Existing unit tests | `tests/test_sessions.py`, `tests/test_conversational_estimation_service.py` |
| Existing router tests (mocked service) | `tests/test_simplified_session_router.py`, `tests/test_sessions_router.py` |

## Documentation plan

- **README.md:** integration test command, attachment path decision, metadata derivation note.
- **docs/technical/README.md:** optional cross-link to session integration coverage (no duplicate contract spec).
- **This work item:** update Verification section on completion.

## Verification (to fill during `/start-task`)

- **Automated:** `uv run pytest tests/test_sessions_integration.py`
- **Manual:** none required if AC-01–AC-12 pass.
- **Not verified yet:** multipart transport (if not implemented), Path A Files API, conversational `ConversationalEstimationService` route wiring.

## Learnings (from related features)

- Do **not** import non-existent helpers (feature-018: `acomplete_structured`); patch `complete_structured` instead.
- Do **not** mock the entire `SimplifiedSessionEstimationService` when the goal is integration coverage — that pattern already exists in `test_simplified_session_router.py` and must not be duplicated.
- Keep `conversation_history` field name (feature-018 rename rejected).
- Register routers only after imports are clean; run `uv run pytest --collect-only` after adding fakes.
- Prefer marker-based assertions over LLM output text matching.

---

**Next step:** implement with:

```text
/start-task docs/work-items/feature-022-session-memory-attachments-integration-tests.md
```

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
| `246df53` | `docs(work-items): add feature-022 session integration tests spec` | Adds canonical work item defining httpx integration harness, LLM fake, fixtures, and mandatory session scenarios. |
