# Feature: Runtime Config Redis Endpoints (Phase 1 parity)

## Objective

Port **runtime model and retrieval configuration** from the official master into `master-ia`:

1. `RuntimeModelConfig` and `RuntimeRetrievalConfig` with Redis-backed overrides.
2. HTTP API: `GET/PUT /api/v1/config/models` and `GET/PUT /api/v1/config/retrieval`.
3. Retrieval and RAG paths honor runtime retrieval toggles (e.g. rerank) without server restart.

This is **Phase 1 parity** child slice after `feature-056-api-security-rate-limit-request-id`.

## Context

### Official reference

| Artifact | Official path | Behavior |
| --- | --- | --- |
| Runtime config | `estimator/app/foundation/llm/runtime_config.py` | Redis JSON blobs, merge with env defaults |
| Config routes | `estimator/app/api/config.py` | GET/PUT models + retrieval |

### `master-ia` fork choices

- Reuse existing `redis` dependency and `Settings.redis_url`.
- Stdlib logging only; no `structlog`.
- When Redis unavailable, fall back to env `Settings` (documented).
- Config routes are **open in dev** (no API keys on config endpoints in this slice); retrieval/RAG routes keep feature-056 auth when keys set.

### Parent roadmap

- Depends on: feature-056 (merged or on base branch).
- Blocks: Phase 2 runtime toggles for hallucination gate, augmentation, etc.

## Scope

### Includes

- `app/services/runtime_config.py` — load/save model + retrieval config from Redis.
- `app/routers/runtime_config.py` — four endpoints under `/api/v1/config/*`.
- Pydantic schemas for request/response bodies.
- Wire `RetrievalService` / RAG path to read retrieval config (at minimum `rerank_enabled` override).
- Settings: document `RUNTIME_CONFIG_REDIS_PREFIX` or reuse key namespace.
- Unit tests with `fakeredis` or mocked Redis client.
- `.env.example` + README subsection.

### Excludes

- Runtime toggles for every Phase 2 flag (hallucination, augmentation) — stub fields OK if forward-compatible.
- Securing config endpoints with API keys (future).
- `structlog`.

## Functional Requirements

- **FR-01:** `GET /api/v1/config/retrieval` returns effective config (Redis override merged over `Settings`).
- **FR-02:** `PUT /api/v1/config/retrieval` persists override to Redis; subsequent `POST /api/v1/retrieval` honors `rerank_enabled`.
- **FR-03:** `GET/PUT /api/v1/config/models` expose at least `structured_model` / `judge_model` overrides (names aligned with existing settings).
- **FR-04:** Invalid body → 422; Redis errors → 503 with safe message.
- **FR-05:** When Redis URL empty or connection fails, GET returns env defaults; PUT returns 503.
- **FR-06:** Layering: routers → `runtime_config` service → Redis; no reverse imports from `embedding_pipeline` to routers.

## Technical Approach

### Module layout

```text
app/services/runtime_config.py
app/schemas/runtime_config.py
app/routers/runtime_config.py
app/main.py                    # register router
tests/test_runtime_config.py
tests/test_runtime_config_api.py
```

### Redis key pattern

```text
master-ia:runtime:retrieval
master-ia:runtime:models
```

### Integration point

`RetrievalService` or router dependency resolves effective `rerank_enabled` via `get_effective_retrieval_config(settings)`.

## Acceptance Criteria

- [ ] **AC-01:** `PUT /api/v1/config/retrieval` with `{"rerank_enabled": false}` changes behavior on next retrieval call (unit test with mock).
- [ ] **AC-02:** `GET` after `PUT` returns persisted values.
- [ ] **AC-03:** Without Redis, `GET` returns settings defaults; `PUT` fails gracefully.
- [ ] **AC-04:** `uv run pytest tests/test_runtime_config*.py` passes without real Redis.
- [ ] **AC-05:** `.env.example` documents any new prefix variable.
- [ ] **AC-06:** Feature-056 regression: retrieval/RAG auth tests still pass.

## Test Plan

### Unit tests

- Merge logic: env defaults + Redis override.
- Serialization round-trip.

### API tests (TestClient)

- GET defaults.
- PUT + GET round-trip.
- Retrieval honors rerank toggle (mock embedder/reranker).

## Verification

| Check | Command |
| --- | --- |
| Runtime config tests | `uv run pytest tests/test_runtime_config.py tests/test_runtime_config_api.py -q` |
| Security regression | `uv run pytest tests/test_api_security.py -q` |
| Fast suite | `uv run pytest` |

## Documentation Plan

| Artifact | Update |
| --- | --- |
| `.env.example` | Redis prefix if added |
| `README.md` | Runtime config API examples |
| `docs/arquitectura-estimador-cag.html` | Config endpoints + Redis flow (mandatory) |
| `feature-053` progress | Phase 1 runtime config row |

## Implementation Plan

- [ ] **Step 1:** Schemas + `runtime_config.py` pure merge/load/save (TDD).
- [ ] **Step 2:** Router GET/PUT + TestClient tests.
- [ ] **Step 3:** Wire retrieval effective config.
- [ ] **Step 4:** Docs, architecture HTML, `.env.example`.

## Estimation

- Size: **M**
- Estimated time: **3–4 hours**
- Planned steps: **4**

## Implementation progress

- [ ] Step 1: Service + schemas (TDD)
- [ ] Step 2: HTTP routes
- [ ] Step 3: Retrieval integration
- [ ] Step 4: Docs + architecture HTML

## Pull Request

- **Branch:** `feature/057-runtime-config-redis-endpoints`
- _(URL after WIP PR opened)_

## How to start

```text
/start-task docs/work-items/feature-057-runtime-config-redis-endpoints.md
```

Parent: `docs/work-items/feature-053-official-master-parity-alignment.md` Phase 1.
