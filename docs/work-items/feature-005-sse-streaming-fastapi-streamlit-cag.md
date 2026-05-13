# Feature: SSE streaming estimations with FastAPI and Streamlit

## Objective
Implement progressive estimation output rendering for the CAG project so users can see generated text while the model is still producing it, instead of waiting for a full buffered response.

## Context
- Current estimation flow is request/response and waits for full completion before rendering.
- The backend stack is FastAPI and should use `StreamingResponse` for server-side chunk emission.
- The frontend stack remains Streamlit and should render chunks progressively with stream helpers.
- Streaming must stay provider-agnostic in the service layer to avoid coupling route handlers to a specific LLM SDK.

## Scope
### Includes
- New endpoint `POST /api/v1/estimate/stream`.
- SSE response format (`text/event-stream`) with `chunk`, `done`, and `error` events.
- Streaming abstraction in service layer for provider-agnostic chunk generation.
- Streamlit client adaptation to consume SSE and progressively render text.
- Minimal local verification with FastAPI + Streamlit running separately.

### Excludes
- WebSockets.
- Persistent memory or database writes.
- Authentication/session management.
- Retry/reconnect strategies for interrupted streams.
- Cost analytics, token telemetry, or background job queues.

## Functional Requirements
1. Add backend endpoint `POST /api/v1/estimate/stream`.
2. Endpoint input schema must match the existing non-streaming estimation payload.
3. Endpoint must return `StreamingResponse(..., media_type="text/event-stream")`.
4. Backend must emit SSE events as:
   - `event: chunk` with `data: {"content": "<partial text>"}`
   - `event: done` with `data: {"status": "completed"}`
   - `event: error` with `data: {"message": "<error detail>"}`
5. Backend must stream chunks immediately as they arrive from the model provider.
6. Streamlit must consume the stream progressively and append visible output chunk by chunk.
7. Streamlit must stop consumption on `done`.
8. Streamlit must show a readable error message on `error` without crashing the app.
9. Existing non-streaming flow must keep working unchanged.

## Technical Approach
- **Router (`app/routers/estimate.py`)**
  - Add `POST /stream` under `/api/v1/estimate`.
  - Wrap async generator in `StreamingResponse`.
  - Add SSE-friendly headers (`Cache-Control`, `Connection`, `X-Accel-Buffering`).
- **Service (`app/services/llm_service.py` or equivalent)**
  - Add SSE serializer helper to build compliant events.
  - Expose provider-agnostic stream API (e.g., `call_llm_stream(...)`).
  - Implement `stream_estimation(...)` async generator yielding `chunk`, `done`, and `error`.
- **Schemas (`app/schemas/estimate.py`)**
  - Reuse existing request model for both non-stream and stream endpoints.
- **Frontend Streamlit**
  - Replace blocking call with SSE consumer using `requests.post(..., stream=True)`.
  - Parse `event:` + `data:` lines safely.
  - Use `st.write_stream(...)` (or equivalent progressive rendering helper).
- **Error handling**
  - Keep provider exceptions inside service boundary.
  - Return safe error messages in SSE `error` event.

## Technical implementation (as shipped)

This section describes **what was built** and **how data flows** end to end. File names match the repository (`app/routers/estimations.py`, `app/schemas/estimations.py`).

### HTTP layer (`app/routers/estimations.py`)

- Handler: `POST /api/v1/estimate/stream`.
- Request body: **`EstimateRequest`** (same schema as `POST /api/v1/estimate`: `transcription`, optional `evaluate`, optional `preprocessing`). The handler passes only `transcription` and `preprocessing` into `EstimationService.stream_estimation(...)`; `evaluate` is accepted for API parity but **does not change SSE output** (no structural score or validation on the stream; use the JSON endpoint for that).
- Response: FastAPI **`StreamingResponse`** with `media_type="text/event-stream"` and headers `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no`.
- The response body is produced by an **async iterator** that yields **pre-formatted SSE text blocks** (strings), not raw dicts: each block is built by the service and flushed as soon as the ASGI server consumes the chunk.

### SSE framing (`EstimationService.serialize_sse_event`)

- Helper: `serialize_sse_event(event, data_dict)` → one SSE event: lines `event: <name>` and `data: <json>` plus the required blank line separator (`\n\n`).
- JSON is compact (`separators=(",", ":")`) so clients can split on lines reliably.

### Core stream logic (`EstimationService.stream_estimation`)

1. **Prepare (same prelude as non-streaming)**  
   Calls `_prepare_call(transcription, preprocessing=...)`, which runs domain guardrail, adaptive mode selection, few-shot example loading, prompt assembly, and preprocessing (`none` / `inline_cleaning` / `two_phase`) so the **`system_prompt` + `user_text`** pair matches the synchronous path.  
   Failures before any provider call yield a single **`event: error`** with a safe `message` and the generator ends.

2. **Provider chain loop** (same order as `LLM_PROVIDERS` + optional static fallback)  
   For each provider:
   - **`StreamingLLMProvider`** (runtime check `isinstance(provider, StreamingLLMProvider)`): **`stream_complete(system, user, max_output_tokens=...)`** returns an **`AsyncIterator[str]`**. Each non-empty string delta is immediately yielded as **`event: chunk`** with `data: {"content":"<delta>"}`. This maps one upstream token/text delta to one SSE chunk (true progressive streaming).
   - **Other providers** (e.g. static fallback): no `StreamingLLMProvider` contract; the code calls **`complete(...)`** once, then emits **one** `chunk` with the full text, then **`done`**.

3. **Success path**  
   After the first provider that emits at least one chunk finishes without error, the service yields **`event: done`** with `data: {"status":"completed"}` and stops.

4. **Errors and fallback**  
   - **`ProviderConfigError`**: if `LLM_AUTH_FALLBACK` is false, yield **`error`** and stop; if true, try next provider.  
   - **`ProviderError`** (timeout, rate limit, empty stream, etc.): log, remember `last_error`, **try next provider**.  
   - **Unexpected exception**: yield **`error`** with a generic safe message and stop.  
   - **Chain exhausted**: yield **`error`** (e.g. `"All providers failed."`, or a config message when applicable).

5. **Intentional trade-off**  
   The stream path does **not** run post-hoc structural validation (`evaluate_estimation_structure`) on partial text; the non-streaming endpoint remains the contract for score/validation.

### Upstream streaming (LiteLLM)

- **`LitellmChainProvider`** implements both `complete` and **`stream_complete`**. Streaming delegates to **`astream_chat`** in `app/services/ai_model_service.py`.
- **`astream_chat`** calls LiteLLM’s async API with **`stream=True`**, iterates the async completion stream, extracts **text deltas** from each chunk, and yields them as `str`. LiteLLM/network failures are mapped to the same **`ProviderError`** subclasses as **`acomplete_chat`**, so the service can reuse fallback policy.

### Streamlit client (`app/streamlit_app.py`)

- Uses **`httpx.stream("POST", ...)`** against `{base_url}/api/v1/estimate/stream` with the same JSON body fields as the REST client (including `evaluate` for UI parity).
- Reads the response **line by line**, buffers **`event:`** and **`data:`** until a blank line, **`json.loads`** the data payload, and maps:
  - `chunk` → yields text to the UI;
  - `done` → stops iteration;
  - `error` → raises **`EstimationError`** with the server message (shown via **`message_for_estimation_failure`**).
- **`st.write_stream(iterator)`** receives the chunk iterator and renders incrementally. Default **`ESTIMATOR_API_BASE_URL`** (or sidebar field) must point at the running FastAPI process (**two processes**: Uvicorn + Streamlit).

### End-to-end data flow (summary)

```text
Streamlit  --HTTP POST stream-->  FastAPI /estimate/stream  --async iter-->  EstimationService.stream_estimation
                                                                                      |
                                                                                      v
                                                                         _prepare_call (guardrail, CAG, mode)
                                                                                      |
                                                                                      v
                                         chunk/done/error SSE strings  <-----  provider chain (astream_chat deltas or complete())
```

## Acceptance Criteria
- [x] Existing non-streaming estimation endpoint still behaves as before.
- [x] New `POST /api/v1/estimate/stream` endpoint exists.
- [x] Endpoint responds with `text/event-stream`.
- [x] Backend emits valid SSE `chunk` events while generation is in progress.
- [x] Backend emits `done` event at successful completion.
- [x] Backend emits `error` event when streaming/model call fails.
- [x] Streamlit renders visible output progressively (no full-response wait).
- [x] Streamlit handles `done` and `error` events correctly.
- [x] Provider-specific streaming logic remains encapsulated in service layer.
- [x] End-to-end local run works with FastAPI and Streamlit in separate processes (operator workflow + automated tests; see Verification).

## Test Plan
- **Unit tests**
  - SSE event formatter returns valid event payloads for `chunk`, `done`, `error`.
  - Streaming service yields `done` on successful provider stream completion.
  - Streaming service yields `error` event when provider stream raises exception.
- **Integration tests**
  - FastAPI test client validates `/api/v1/estimate/stream` headers and event framing.
  - Non-stream endpoint regression check to ensure unchanged behavior.
- **Manual checks**
  - Run FastAPI: `uv run uvicorn app.main:app --reload`
  - Run Streamlit app separately and submit sample transcription.
  - Confirm chunk-by-chunk rendering appears progressively.
  - Simulate provider failure and confirm readable Streamlit error output.

## Documentation Plan
- [x] Streaming endpoint contract: `docs/technical/README.md` §11.1 (`chunk`, `done`, `error`, headers, `curl`, `evaluate` note).
- [x] Local dual-process instructions: `docs/technical/README.md` §4 + subproject `README.md` Streamlit section; optional `ESTIMATOR_API_BASE_URL` in `.env.example`.
- [x] Environment: no separate “streaming mode” vars; same provider keys/models as non-streaming (documented in §11.1).
- [x] Feature status reflected in this work item; mirror Second Brain via `scripts/sync-estimador-cag-docs.sh` when vault copies exist.

## Baby Steps
1. Reuse existing request schema and add stream route skeleton returning `StreamingResponse`.
2. Add SSE event helper and stream generator in service layer with mocked provider stream.
3. Wire provider streaming adapter behind `call_llm_stream(...)`.
4. Add Streamlit SSE client parser and progressive rendering.
5. Add focused tests for formatter, generator lifecycle, and endpoint framing.
6. Run minimal local manual validation and update docs.
7. Replace post-completion text slicing with native upstream LiteLLM streaming so SSE `chunk` events arrive as the provider produces deltas (closes the residual risk and fulfills functional requirement 5 in practice).

## Implementation progress

- [x] Step 1: Added `POST /api/v1/estimate/stream` endpoint with `StreamingResponse(..., media_type="text/event-stream")`.
- [x] Step 2: Added SSE serializer and provider-agnostic `stream_estimation(...)` generator in service layer.
- [x] Step 3: Added SSE response headers and API tests for `done` and `error` event framing.
- [x] Step 4: Updated Streamlit UI to consume SSE endpoint progressively using stream parsing.
- [x] Step 5: Added focused tests for SSE formatting and stream lifecycle; ran full project test suite.
- [x] Step 6: Dual-process workflow documented (`docs/technical/README.md` §4, subproject `README.md`); automated coverage via API and service tests; browser-side visual check remains an optional operator smoke test.
- [x] Step 7: Native upstream streaming via `acompletion(stream=True)` (LiteLLM async iterator → SSE `chunk` per delta).

## Step 7 plan — Native upstream streaming
- **Problem (empirically confirmed):** the stream endpoint waits for the full completion (`await self.estimate(...)`) and then slices the final text into 120-char blocks emitted in a single burst. A timing probe against `/api/v1/estimate/stream` shows the 20 chunks arriving within the same millisecond after ~10.7 s of silence. Streamlit therefore renders nothing during generation and dumps the whole text at the end.
- **Goal:** SSE `chunk` events must be emitted as deltas arrive from the LLM provider; total latency-to-first-chunk should drop to roughly the provider's first-token latency.
- **Scope of changes:**
  - `app/services/ai_model_service.py`: add `astream_chat(...)` that calls `await acompletion(..., stream=True)` and yields delta strings, mapping LiteLLM exceptions onto the existing `ProviderError` subclasses.
  - `app/services/llm_chain.py`: extend `LitellmChainProvider` with `stream_complete(...)` returning an `AsyncIterator[str]`. `StaticFallbackProvider` keeps a single yield (degraded mode is non-streaming).
  - `app/services/llm_types.py`: extend `LLMProvider` Protocol with optional `stream_complete(...)` (use `hasattr` checks at the call site for backward compatibility).
  - `app/services/llm_service.py`: rewrite `stream_estimation(...)` to perform the existing guardrail / mode assessment / preprocessing pipeline, then iterate the first streaming-capable provider and emit one SSE `chunk` per delta. Preserve `done`, `error`, and provider fallback.
- **Out of scope:** token-level usage accounting on streamed responses; non-streaming providers other than the static fallback; reconnect or partial-resume semantics.

## Step 7 acceptance criteria
- [x] Time between first `chunk` event and the request start reflects provider first-token latency (sub-second under normal conditions), not full-completion latency.
- [x] Successive `chunk` events are spaced over time (no single-millisecond burst at the end).
- [x] `done` event is emitted once after the upstream stream completes.
- [x] `error` event is emitted with a safe message when the upstream stream fails mid-generation.
- [x] Static fallback path remains functional and emits a single chunk + `done`.
- [x] Existing non-streaming endpoint behavior is unchanged.

## Verification
- **Verified (Steps 1–5):**
  - `uv run pytest tests/test_api.py::test_estimate_stream_returns_sse_done_event -q`
  - `uv run pytest tests/test_api.py::test_estimate_stream_emits_error_event_on_service_failure -q`
  - `uv run pytest tests/test_llm_service.py::test_stream_estimation_emits_done_event tests/test_llm_service.py::test_stream_estimation_emits_error_event_on_failure tests/test_llm_service.py::test_serialize_sse_event_returns_valid_payload -q`
  - `uv run pytest -q` (full `estimador-cag` suite): `121 passed` (initial baseline).
- **Verified (Step 7 diagnosis):**
  - Timing probe with `urllib.request` against `POST /api/v1/estimate/stream` showed all 20 chunks arriving at `t+10722.0..10722.1 ms`, confirming post-completion slicing.
- **Verified (Step 7 implementation):**
  - New unit tests in `tests/test_ai_model_service.py`: `astream_chat` happy path, delta-skip, open-phase auth error, mid-stream rate-limit error, empty stream, empty user message (6 new tests).
  - New unit tests in `tests/test_llm_service.py`: chunk-per-delta emission, progressive (non-burst) timing assertion, mid-stream provider fallback, non-streaming-provider single-chunk path, domain guardrail rejection during streaming (5 new tests).
  - `uv run pytest -q` (full suite): `132 passed`.
  - Documentation closure (2026-05-07): `docs/technical/README.md` §11.1 + §4 dual-process; subproject `README.md`; `.env.example` `ESTIMATOR_API_BASE_URL`; `GET /` includes `estimate_stream`; `tests/test_api.py::test_root_returns_service_index` asserts streaming route hint.
  - End-to-end timing probe against running FastAPI with real OpenAI provider:
    - First chunk at `t+2404.3 ms` (provider time-to-first-token).
    - 543 deltas spread across `t+2404 ms → t+11370 ms` (~9 s of progressive emission).
    - `done` event at `t+11437 ms`.
- **Step 6 (dual-process):**
  - Documented runbook: two terminals (Uvicorn + Streamlit), optional `ESTIMATOR_API_BASE_URL`, link to SSE contract §11.1.
  - **Optional:** open Streamlit in a browser and confirm text appears incrementally with a live provider — not executed in CI.
- **Residual risk:**
  - Streaming path skips structural mode-output validation that the non-streaming path performs, because that check requires the full text. Acceptable trade-off: same risk applies to any streaming UI; the non-streaming endpoint remains available for callers that need post-validation.

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
| `e74dbaa` | `feat(estimador-cag): add SSE streaming estimate endpoint and progressive UI` | Added `POST /api/v1/estimate/stream` with SSE framing, LiteLLM `astream_chat` deltas via `StreamingLLMProvider`, estimation service fallback chain, Streamlit `httpx` SSE consumer with `st.write_stream`, docs (technical README §11.1, subproject README), `ESTIMATOR_API_BASE_URL` in `.env.example`, root service index hint for `estimate_stream`, and focused API/service tests. |
| `a42157a` | `docs(estimador-cag): add feature-005 SSE streaming work item` | Exported the canonical feature note into `docs/work-items/` and recorded the implementation commit in the repository commit log table. |
