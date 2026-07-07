# Feature: API Security, Rate Limiting, and Request ID (Phase 1 parity)

## Objective

Port **Session 9 API hardening** from the official master (`ai-engineering` / `estimator`) into `master-ia` for the retrieval and RAG estimate surfaces:

1. Optional API-key auth (`RETRIEVAL_API_KEY`, `ESTIMATE_API_KEY`).
2. Per-key rate limits via `slowapi` (retrieval 120/min, RAG estimate 10/min).
3. Global `X-Request-ID` correlation on every HTTP response and in stdlib logs.

This is **child slice Step 2** of `docs/work-items/feature-053-official-master-parity-alignment.md`. It does not add runtime Redis config (feature-057) or RAGAS gate (separate work item).

## Context

### Official reference

| Artifact | Official path | Behavior |
| --- | --- | --- |
| API keys | `estimator/app/api/security.py` | `X-API-Key` header, `secrets.compare_digest`, independent retrieval vs estimate keys |
| Rate limits | `estimator/app/api/rate_limiting.py` | slowapi bucket = API key (fallback IP), 429 + `Retry-After` |
| Request ID | `estimator/app/main.py` | Middleware binds id; official uses structlog contextvars |

### `master-ia` fork choices (deliberate)

- **Open access when keys unset:** if `RETRIEVAL_API_KEY` / `ESTIMATE_API_KEY` are empty, routes stay open (local dev default). Official `.env.example` always sets demo keys.
- **Rate limits opt-in:** `RATE_LIMIT_ENABLED=false` by default so the fast pytest suite and local dev are unchanged; enable explicitly in staging/prod.
- **Stdlib logging only:** `RequestIdLogFilter` injects `request_id` on log records — no `structlog`.
- **Scoped routes:** only `POST /api/v1/retrieval` and `POST /api/v1/estimate/rag` are secured. CAG v1/v2, sessions, embeddings ingest remain unchanged.

### Parent roadmap

- Depends on: nothing (Phase 1 entry point after feature-052).
- Blocks: `feature-057-runtime-config-redis-endpoints` (runtime toggles on secured routes).

## Scope

### Includes

- Settings: `RETRIEVAL_API_KEY`, `ESTIMATE_API_KEY`, `RATE_LIMIT_ENABLED`.
- `app/middleware/security.py` — `require_retrieval_key`, `require_estimate_key`.
- `app/middleware/rate_limiting.py` — slowapi limiter + `conditional_rate_limit`.
- `app/middleware/request_id.py` — middleware + logging filter.
- `app/deps.py` — `get_request_id(request)`.
- Wire auth + limits on `app/routers/retrieval.py` and `app/routers/rag_estimations.py`.
- Register limiter + exception handler + middleware in `app/main.py`.
- Unit/integration tests with mocked downstream services.
- `.env.example` placeholders.

### Excludes

- Securing CAG `/api/v1/estimate`, `/api/v2/estimate`, session routes, or embeddings ingest.
- Runtime model/retrieval config (feature-057).
- Idempotency headers (feature-062 / Phase 2).
- `structlog` migration.
- Committing generated eval artifacts.

## Functional Requirements

- **FR-01:** When `RETRIEVAL_API_KEY` is non-empty, `POST /api/v1/retrieval` without a matching `X-API-Key` returns **401**; with the correct key returns the normal response.
- **FR-02:** When `ESTIMATE_API_KEY` is non-empty, `POST /api/v1/estimate/rag` follows the same 401/200 contract with its own key.
- **FR-03:** Retrieval and estimate keys are **independent** (retrieval key must not unlock RAG and vice versa).
- **FR-04:** When both key env vars are empty, retrieval and RAG routes remain **open** (no 401).
- **FR-05:** Keys compared with `secrets.compare_digest` (constant-time).
- **FR-06:** When `RATE_LIMIT_ENABLED=true`, retrieval is limited to **120/minute** and RAG estimate to **10/minute** per API-key bucket (IP fallback when no key header).
- **FR-07:** Rate-limit breach returns **429** with JSON body (`detail`, `limit`, `retry_after_seconds`) and `Retry-After: 60` header.
- **FR-08:** Every HTTP response includes **`X-Request-ID`**; client-supplied id is echoed when present.
- **FR-09:** Handlers use `get_request_id(request)` instead of ad-hoc `uuid4()` prefixes for correlation.
- **FR-10:** Log records during a request expose `request_id` via stdlib filter (no structlog).

## Technical Approach

### Module layout

```text
app/middleware/security.py       # API key dependencies
app/middleware/rate_limiting.py  # slowapi limiter + conditional decorator
app/middleware/request_id.py     # correlation middleware + RequestIdLogFilter
app/deps.py                      # get_request_id()
```

### Router wiring

```python
@router.post(..., dependencies=[Depends(require_retrieval_key)])
@conditional_rate_limit("120/minute")
async def retrieve_chunks(request: Request, payload: RetrievalRequest, ...):
    request_id = get_request_id(request)
```

RAG route mirrors with `require_estimate_key` and `10/minute`.

### Dependency

- `slowapi` (added via `uv add slowapi`).

### Settings (`.env.example`)

```text
RETRIEVAL_API_KEY=
ESTIMATE_API_KEY=
RATE_LIMIT_ENABLED=false
```

## Acceptance Criteria

- [x] **AC-01:** With `ESTIMATE_API_KEY` set, `POST /api/v1/estimate/rag` without key → 401; with key → 200 (mocked service).
- [x] **AC-02:** With `RETRIEVAL_API_KEY` set, `POST /api/v1/retrieval` without key → 401; with key → 200.
- [x] **AC-03:** Keys are independent (cross-key requests → 401).
- [x] **AC-04:** With keys unset, retrieval accepts unauthenticated POST.
- [x] **AC-05:** With `RATE_LIMIT_ENABLED=true`, 11th RAG request within a minute → 429 + `Retry-After`.
- [x] **AC-06:** `GET /health` response includes `X-Request-ID`; client id echoed when sent.
- [x] **AC-07:** `README.md` documents new env vars and curl examples with `X-API-Key`.
- [x] **AC-08:** `uv run pytest` fast suite green (excluding pre-existing shell-env `test_config` failures).
- [x] **AC-09:** CAG v1/v2 and session estimate tests unchanged (no auth regression).

## Test Plan

### Automated

| File | Coverage |
| --- | --- |
| `tests/test_api_security.py` | 401/200 boundaries, key independence, open access when unset |
| `tests/test_api_rate_limiting.py` | 429 on 11th RAG call when limits enabled |
| `tests/test_request_id_middleware.py` | `X-Request-ID` header presence and echo |
| `tests/test_rag_estimation_endpoint.py` | RAG regression (no keys in test env) |
| `tests/embedding_pipeline/test_retrieval_router.py` | Retrieval regression |

Commands:

```bash
uv run pytest tests/test_api_security.py tests/test_api_rate_limiting.py tests/test_request_id_middleware.py -q
uv run pytest -q
```

### Manual

1. Set `ESTIMATE_API_KEY=test-key` in `.env`, restart API, curl RAG without/with header.
2. Set `RATE_LIMIT_ENABLED=true`, hammer RAG endpoint, confirm 429.
3. Confirm `X-Request-ID` in Swagger response headers on `/health`.

## Verification

| Check | Result |
| --- | --- |
| Targeted security/rate/id tests | **Verified** — 10 passed (2026-07-06) |
| Full fast pytest | **Verified** — 667 passed; 2 pre-existing `test_config` failures when shell sets `DATABASE_URL` / `RETRIEVAL_RERANK_ENABLED` |
| README curl examples | **Verified** — Security § API hardening + Configuration table (2026-07-06) |
| Live staging with real keys | **Not verified** |

**Residual risk:** `conditional_rate_limit` reads `get_settings()` at request time; tests must patch `app.middleware.rate_limiting.get_settings` when overriding `rate_limit_enabled` (cached `lru_cache` on config module).

## Documentation Plan

| Artifact | Status |
| --- | --- |
| `.env.example` | Done |
| `README.md` | Done — API hardening subsection |
| `docs/technical/README.md` | Optional — cross-link when parity matrix row updated |
| `feature-053` progress | Updated with PR link |

## Implementation Plan

- [x] **Step 1:** Add `slowapi` + settings + `.env.example`.
- [x] **Step 2:** `security.py` + `tests/test_api_security.py` (TDD).
- [x] **Step 3:** `request_id.py` + `tests/test_request_id_middleware.py`.
- [x] **Step 4:** `rate_limiting.py` + wire `main.py` + rate limit test.
- [x] **Step 5:** Wire `retrieval.py` + `rag_estimations.py` with `get_request_id`.
- [x] **Step 6:** README subsection + mark AC-07; `/finish-task` closure.

## Estimation

- Size: **S**
- Estimated time: **2–3 hours**
- Planned steps: **6** (complete)

## Implementation progress

- [x] Step 1: Dependencies + settings
- [x] Step 2: API key auth
- [x] Step 3: Request ID middleware
- [x] Step 4: Rate limiting
- [x] Step 5: Router wiring
- [x] Step 6: README + closure prep

## Pull Request

- **Merged:** https://github.com/povedica/master-ia-lidr/pull/48 (2026-07-07)
- **Branch:** `feature/056-api-security-rate-limit-request-id` (deleted after merge)

## Repository commits (master-ia)

| Commit | Summary |
| --- | --- |
| _(on branch)_ | `feat(api): add optional API keys, rate limits, and request ID middleware` |
| _(on branch)_ | `docs(feature-053): record feature-056 WIP PR and Step 2 progress` |
| _(on branch)_ | `docs(readme): document API hardening env vars and curl examples (feature-056)` |

## Handoff from feature-056

**Shipped interfaces**

- `POST /api/v1/retrieval` — optional `require_retrieval_key` + `120/minute` when `RATE_LIMIT_ENABLED=true`
- `POST /api/v1/estimate/rag` — optional `require_estimate_key` + `10/minute` when limits enabled
- Global `request_id_middleware` + `RequestIdLogFilter`; `get_request_id(request)` in `app/deps.py`
- Settings: `RETRIEVAL_API_KEY`, `ESTIMATE_API_KEY`, `RATE_LIMIT_ENABLED` (see `.env.example`)

**Verification evidence**

- `uv run pytest tests/test_api_security.py tests/test_api_rate_limiting.py tests/test_request_id_middleware.py` — 10 passed
- Full fast suite green except pre-existing shell-env `test_config` failures when `DATABASE_URL` / `RETRIEVAL_RERANK_ENABLED` are set in the shell

**Not verified**

- Live staging with real keys and `RATE_LIMIT_ENABLED=true` under load

**Residual risks**

- Tests overriding `rate_limit_enabled` must patch `app.middleware.rate_limiting.get_settings` (cached `lru_cache` on config)
- CAG/session/embeddings routes remain unsecured by design until a future work item

**Recommended first tests for feature-057**

- Confirm runtime config endpoints respect the same auth dependencies when wired
- Regression: retrieval/RAG tests with keys unset (default open access)

## How to start

```text
/start-task docs/work-items/feature-056-api-security-rate-limit-request-id.md
```

For program context, see `docs/work-items/feature-053-official-master-parity-alignment.md` Step 2.
