# Feature: Exact-Match Cache Layer for LLM Estimation Responses

## Objective

Add a Redis-backed exact-match cache so repeated estimation requests with identical prompt-affecting inputs reuse a stored LLM result, reducing cost and latency. The cache is the first layer only (no semantic similarity).

## Context

- Estimates are produced from meeting transcriptions via CAG in `EstimationService` (`app/services/llm_service.py`), orchestrated from `POST /api/v1/estimate` in `app/routers/estimations.py`.
- Responses are shaped by `EstimateResponse` (`app/schemas/estimations.py`) and assembled via `assemble_estimate_response` (`app/services/estimate_response_builder.py`).
- Settings live in `app/config.py` (`Settings`, `get_settings`); there is no `core/settings.py` in this project.
- Provider stack uses LiteLLM-style routing (`app/services/llm_chain.py`, `ai_model_service.py`). No `temperature` parameter is currently referenced in the codebase; the cache key contract must still reserve a slot for it when generation parameters are added or forwarded.

## Scope

### Includes

- Redis-backed storage with configurable URL, TTL, namespace, and enable/disable flag.
- Deterministic cache keys from a normalized JSON payload (sorted keys, UTF-8, SHA-256), prefixed by namespace.
- Lookup before any LLM call; on hit, skip providers and return cached estimation payload.
- Store full cached artifact after miss (estimation text, model, usage-related fields needed to rebuild API semantics; see Technical Approach).
- TTL via `SETEX` (or equivalent) from `LLM_CACHE_TTL_SECONDS` (default 86400).
- Response metadata for cache state (`enabled`, `hit`, `level`, optional `key`).
- Structured logging for hit/miss/store/disabled/error.
- Graceful degradation: if Redis is unavailable, log and continue with normal LLM flow (no user-visible failure solely due to cache).

### Excludes

- Semantic / embedding cache, vector DB, provider prompt caching, invalidation UI, warm-up jobs, distributed metrics dashboard.

## Functional Requirements

### FR-001: Cache key generation

Before calling the LLM, build a deterministic key:

1. Construct a dict (conceptually):

   ```json
   {
     "prompt": "<user transcription after request normalization used for estimation>",
     "system_prompt": "<fully resolved system prompt string sent to the model>",
     "model": "<effective model id used for the completion>",
     "temperature": "<numeric temperature or explicit default if not configurable yet>",
     "context_version": "<CAG context version and/or hash of static context affecting output>"
   }
   ```

2. Serialize with `json.dumps(..., sort_keys=True, ensure_ascii=False)`, encode UTF-8, SHA-256 hex digest.

3. Final key: `{LLM_CACHE_NAMESPACE}:{digest}`  
   Example pattern: `llm:estimation:<sha256_hex>` when namespace is `llm:estimation`.

**Notes:** Include `preprocessing` mode and any value that changes the resolved system prompt or user message (e.g. mode-specific prompts, examples content). Align `context_version` with existing version constants (`PROMPT_VERSION`, `EXAMPLES_VERSION` in `llm_service.py`) plus a hash of loaded example content if versions alone are insufficient.

### FR-002: Cache lookup before LLM call

When cache is enabled:

- `GET` equivalent for the key before provider invocation.
- On hit: do not call LLM; return cached estimation data; set `cache.hit = true`, `cache.level = "exact"`.

### FR-003: Cache storage after LLM call

On miss:

- Run existing estimation pipeline.
- Persist a JSON payload sufficient to reconstruct `EstimationResult` / API layer needs (at minimum: `estimation`, `model`, token counts; include `provider`, `mode`, `finish_reason`, guardrail-related fields if they affect downstream assembly).
- Use TTL from settings.

Return `cache.hit = false`.

### FR-004: Cache TTL

- Env: `LLM_CACHE_TTL_SECONDS` (default `86400`).

### FR-005: Cache activation flag

- Env: `LLM_CACHE_ENABLED` (default adopt `false` for safe rollout or `true` per product decision; document chosen default in `.env.example`).
- When disabled: no Redis connection attempts for cache path; behave as today.

### FR-006: Response metadata

Extend API response with a `cache` object, for example:

```json
{
  "estimation": "...",
  "model": "gpt-4o-mini",
  "usage": { "tokens_in": 3500, "tokens_out": 900 },
  "cache": {
    "enabled": true,
    "hit": true,
    "level": "exact",
    "key": "llm:estimation:..."
  }
}
```

If exposing full key is undesirable externally, omit `key` from default responses or gate behind `DEV_MODE` / separate flag.

## Technical Approach

### Module boundaries

- Add `app/services/cache_service.py` (or `llm_cache.py`): key construction, Redis get/set, JSON serialization, TTL; **no** provider-specific logic.
- Wire cache orchestration at the boundary where `EstimationResult` is produced—preferably inside `EstimationService.estimate` or a thin façade called by it—so routers stay thin.
- Extend `Settings` in `app/config.py` with cache-related fields and validation (e.g. require `LLM_CACHE_REDIS_URL` when enabled).
- Extend `EstimateResponse` with an optional `cache: CacheMetadataView | None` (new small Pydantic model).
- Populate cache metadata in `assemble_estimate_response` or immediately after `service.estimate` in the router (pick one place to avoid duplication).

### Dependencies

- Add `redis` (e.g. `redis>=5,<6`) via `uv add redis` at the repository root.

### Environment variables

| Variable | Purpose |
|----------|---------|
| `LLM_CACHE_ENABLED` | Master switch |
| `LLM_CACHE_REDIS_URL` | Redis DSN (e.g. `redis://localhost:6379/0`) |
| `LLM_CACHE_TTL_SECONDS` | TTL (default `86400`) |
| `LLM_CACHE_NAMESPACE` | Key prefix (default `llm:estimation`) |

Document all in `.env.example` and project README / `docs/technical/README.md`.

### Stored value shape (recommended)

```json
{
  "content": "<estimation markdown>",
  "model": "<string>",
  "provider": "<string>",
  "tokens_in": 0,
  "tokens_out": 0,
  "created_at": "2026-05-06T10:30:00Z"
}
```

Map to/from `UsageInfo` and `EstimationResult` fields.

### Logging

Emit structured logs (stable event names), minimum:

- `cache.hit`, `cache.miss`, `cache.store`, `cache.disabled`, `cache.error`

Include: `cache_level` (`exact`), `model`, `namespace`, and on error `error_type` without secrets.

### Failure handling

On Redis errors: log `cache.error`, proceed without cache (same as miss). Optional short circuit to disable client for the remainder of the process is out of scope unless needed.

## Acceptance Criteria

- [ ] **AC-001:** First request for a novel payload calls LLM, writes Redis, returns `cache.hit=false`.
- [ ] **AC-002:** Identical inputs reuse cache, no LLM call, `cache.hit=true`, `cache.level=exact`.
- [ ] **AC-003:** Changing effective model changes key and forces fresh LLM call.
- [ ] **AC-004:** Changing resolved system prompt or CAG-affecting context changes key and forces fresh LLM call.
- [ ] **AC-005:** After TTL expiry, entry is treated as miss and LLM is called again.
- [ ] **AC-006:** With `LLM_CACHE_ENABLED=false`, Redis is not queried and behavior matches pre-cache path.
- [ ] **AC-007:** When Redis is down or errors, estimation still succeeds and errors are logged.

## Test Plan

### Unit tests

- Key determinism: same payload → same key; different `model`, `prompt`, `system_prompt`, `temperature`, or `context_version` → different keys.
- JSON round-trip for stored cache records.
- Disabled cache: no Redis client calls (mock Redis).
- Redis error path: mock failure → estimation still returns success from mocked LLM.

### Integration tests

- Use fakeredis or mock Redis client (no real Redis required in CI): first call stores, second call hits cache.
- TTL: advance clock or inject short TTL and assert miss after expiry (if supported by test double).

### Manual checks

- Local Redis: run two identical `curl` requests to `/api/v1/estimate`, confirm second shows cache hit and reduced latency.
- Toggle `LLM_CACHE_ENABLED` and confirm behavior.

## Documentation Plan

- Update `.env.example` with cache variables.
- Update `docs/technical/README.md` (and root estimator README if it lists env vars) with behavior, defaults, and operational notes (Redis requirement when enabled).
- After implementation, sync Second Brain mirror per `scripts/sync-estimador-cag-docs.sh` if vault copy is maintained.

## Baby Steps (implementation order)

1. Add settings + `.env.example` + dependency (`redis`).
2. Implement `CacheService` with key builder and get/set; unit tests for keys and serialization.
3. Integrate into `EstimationService` path with feature flag; unit tests for bypass and Redis failure.
4. Extend `EstimateResponse` and assembly; API tests for metadata.
5. Integration-style tests with mocked Redis; manual Redis smoke test.

## Verification

- `uv run pytest` (repository root) for affected tests.
- Optional: `uv run ruff check` / typecheck if project uses them.

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
| `2d78f10` | `docs(estimador-cag): add feature-007 exact-match LLM cache work item` | Planning/spec only; Redis exact-match cache FR and approach (no runtime code yet). |

Further rows: add during implementation (deps, settings, service, API schema, tests, docs).
