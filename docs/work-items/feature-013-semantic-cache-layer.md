# Feature: Semantic Cache Layer for Guarded LLM Inference

## Problem

The estimation service already has a serious inference path: typed inbound requests, versioned Jinja2 prompts, structured Pydantic responses, and input/output guardrails. The remaining cost and latency problem is that different users can ask for the same underlying estimation intent with different wording, so exact-match caching misses most useful reuse opportunities.

Natural language rarely repeats byte-for-byte. A cache keyed only by raw text, rendered prompt, or request JSON cannot capture reformulations such as:

- "Estimate a SaaS MVP with auth, payments, and admin dashboard."
- "How much work is needed for a subscription web app with login, Stripe, and backoffice?"

The feature must reduce latency and LLM cost without lowering safety. Cache reads must never bypass input guardrails, and cache writes must happen only after the response has passed output validation and guardrails.

## Objective

Design and implement a production-ready semantic cache layer for AI service responses using deterministic bucketization plus vector similarity.

The target behavior:

- A new request that is semantically equivalent to a previous validated request inside the same structural context can return the cached response.
- A request outside the configured similarity threshold, bucket, version, or rollout scope executes the normal LLM flow.
- Only fully validated and guardrail-approved responses are written to the cache.
- The system is observable, configurable, safe to deploy in log-only mode, and replaceable at the infrastructure layer.

## Context

Current relevant code and architecture:

- `app/routers/estimations_v2.py` exposes the structured v2 API and delegates guarded inference to `LLMPipeline`.
- `app/guardrails/llm_pipeline.py` already coordinates input guardrails, provider calls, output semantic validation, final status, and `safe_to_cache`.
- `app/schemas/estimation_request.py` defines the typed inbound request.
- `app/schemas/estimation_result.py` defines the structured domain result.
- `app/schemas/estimation_response.py` defines the v2 transport envelope and already exposes `prompt_version`, `request_id`, `safe_to_cache`, and guardrail status metadata.
- `docs/work-items/feature-007-exact-match-llm-cache.md` planned an exact-match Redis cache, explicitly excluding semantic caching.
- `docs/work-items/feature-011-jinja2-dynamic-prompt-rendering.md` established versioned prompts and Pydantic-first structured output.
- `docs/work-items/feature-012-semantic-guardrails-llm-pipeline.md` established the guarded pipeline and cache safety rules.

This feature should build on the v2 pipeline. It should not contaminate frontend code or unrelated business backend modules with semantic cache decisions.

## Product Hypothesis

If the service computes embeddings after input guardrails and performs vector lookup only within a deterministic cache bucket, then a measurable percentage of estimation requests can avoid the LLM call while preserving response quality.

The threshold is a product decision as much as an engineering setting:

- Too low: higher hit rate, higher false-positive risk.
- Too high: lower risk, lower latency/cost impact.

The first production rollout must therefore run in log-only mode to measure potential hit rate, score distribution, and false positives before bypassing the LLM.

## Scope

### Includes

- Semantic cache lookup for the structured estimation v2 path.
- Deterministic bucket construction from prompt-affecting structured fields.
- Embedding generation for free-text request surface after input guardrails.
- Vector lookup in Redis using Redis vector search, preferably through `redisvl` or equivalent.
- Infrastructure abstraction so the domain/application layer does not depend on Redis-specific APIs.
- Configurable similarity threshold, TTL, namespace, rollout flags, endpoint/operation enablement, and log-only mode.
- Response metadata for cache observability and frontend UX.
- Cache writes only after structured output validation and output guardrails pass.
- Log-only mode for calibration before real serving.
- Metrics, structured logs, and tracing hooks.
- Unit and integration tests with mocked/fake cache and embedding providers.
- Documentation updates for settings, pipeline order, rollout, and operational safety.

### Excludes

- No frontend cache implementation.
- No client-side embedding, threshold, or bucket logic.
- No exact-match-only cache path as the primary solution.
- No cache of errors, timeouts, degraded responses, partial responses, unsafe outputs, or invalid payloads.
- No manual cache invalidation UI in the first implementation.
- No cross-tenant sharing unless explicit tenant isolation and product approval are added.
- No real Redis, OpenAI, Anthropic, or embedding provider calls in the default automated test suite.
- No migration to LangChain, LangGraph, or a broad orchestration framework.

## Architectural Decisions

### AD-01: Guardrails run before cache lookup

Input guardrails must execute before embedding and lookup. A malicious or out-of-domain request must not be able to retrieve a previously valid cached response and skip moderation, PII checks, prompt-injection checks, or domain validation.

Required order:

```text
HTTP request
  -> Pydantic input validation
  -> deterministic input rendering / assessment surface
  -> input guardrails
  -> embedding
  -> semantic cache lookup
  -> cache hit response OR LLM miss path
```

### AD-02: Cache writes happen only after output validation and guardrails

The cache amplifies both good and bad responses. Therefore, write eligibility requires:

- LLM call succeeded.
- Structured output parsed into `EstimationResult`.
- Pydantic validators passed.
- Output semantic guardrails passed.
- `safe_to_cache=True`.
- `safe_to_display=True`.
- Final status is success, not degraded or error.

### AD-03: Composite cache key

The cache key has two parts:

1. **Deterministic bucket**: narrows comparison to the same functional context.
2. **Vector component**: compares semantic similarity of the free-text input inside that bucket.

The lookup gate is two-stage:

```text
same bucket AND vector_similarity >= SEMANTIC_CACHE_SIMILARITY_THRESHOLD
```

### AD-04: Prompt version belongs in the bucket

`prompt_version` must be part of the deterministic bucket. Prompt changes can alter the expected output even when the user intent is the same. Including `prompt_version` causes natural invalidation: a new prompt version writes to a new bucket, while old buckets expire by TTL without manual deletion.

The same principle applies to output schema version, guardrail rules version, and embedding model version when those changes alter behavior or comparability.

### AD-05: Semantic cache is an AI service component

The cache belongs in the inference service layer, not in frontend code or generic backend business logic. Clients may receive simple metadata such as `cached`, `cache_score`, `cache_bucket`, `prompt_version`, and `request_id`, but they must not know how thresholds, vector search, or bucketization work.

### AD-06: Infrastructure is replaceable

Start with Redis vector search because Redis is a realistic cache store and can support TTL plus vector lookup. Keep the domain and application layers behind interfaces so a future migration to `pgvector`, Qdrant, Pinecone, or another vector store does not rewrite the pipeline.

## Functional Requirements

### FR-01: Guarded semantic lookup

The service must run input guardrails before embedding generation or cache lookup. If input guardrails block or degrade a request, the semantic cache must not be queried.

### FR-02: Bucket-scoped vector search

The service must compare vector neighbors only within the same deterministic bucket. A candidate from another prompt version, output format, detail level, tenant, operation, schema version, or materially different structured context is not eligible.

### FR-03: Threshold-gated hits

The service must serve a cached response only when semantic cache serving is enabled, log-only mode is off, the candidate payload validates, and the similarity score is greater than or equal to the configured threshold.

### FR-04: Log-only calibration mode

The service must support a log-only mode that computes embeddings, looks up candidates, records the suggested decision, and still executes the LLM path. Log-only mode must be the default rollout posture before production serving.

### FR-05: Validated cache writes

The service must write cache entries only after the LLM response has passed structured parsing, Pydantic validation, output guardrails, and final safe-to-cache checks.

### FR-06: Observable response metadata

The v2 response must expose cache metadata that is useful for UX and telemetry without leaking raw keys, embeddings, prompts, or sensitive content.

### FR-07: Replaceable infrastructure

The domain/application logic must depend on semantic cache and embedding interfaces, not directly on Redis, RedisVL, or any specific vector database SDK.

## Technical Approach

### Target Pipeline

```text
1. Receive `EstimationRequest`.
2. FastAPI/Pydantic validates input shape.
3. Build request id / trace id and pipeline context.
4. Render canonical guided input or assessment surface.
5. Run input guardrails.
6. If input is blocked or degraded, do not lookup cache.
7. Build deterministic cache bucket.
8. Compute embedding for normalized free-text input.
9. Lookup nearest neighbors inside the same bucket.
10. If semantic cache is disabled: record disabled decision and continue to LLM.
11. If log-only: record top candidate, score, bucket, and suggested decision; continue to LLM.
12. If hit and score >= threshold: load cached artifact, validate it against current schema, return cached response.
13. If miss: render prompt and call LLM through existing service/provider abstraction.
14. Validate structured output with Pydantic.
15. Run output guardrails.
16. If final output is safe and cache-eligible: write semantic cache entry.
17. Return final response with cache metadata.
```

### Minimal Pseudocode

```python
input_phase = await run_input_semantic_phase(...)
if input_phase.blocks_or_degrades:
    return guarded_outcome_without_cache(...)

cache_decision = await semantic_cache.evaluate(request, context)
if cache_decision.should_serve:
    return response_from_cache(cache_decision.entry)

bundle = await estimation_service.estimate_structured(...)
output_results = evaluate_output_semantic_guardrails(...)
outcome = build_final_outcome(bundle, output_results)

if outcome.safe_to_cache:
    await semantic_cache.write(request, context, outcome.bundle)

return response_from_bundle(outcome)
```

This pseudocode is illustrative only. Implementation must follow the existing `LLMPipeline` boundaries and tests.

## Cache Key Design

### Deterministic Bucket

Build a canonical JSON object, serialize it with sorted keys, and hash it. Recommended bucket fields:

- `cache_schema_version`
- `operation` or `feature`, for example `estimation_v2`
- `tenant_id` or `workspace_id` when available; otherwise explicit `"default"` until multitenancy exists
- `prompt_version`
- `examples_version`
- `output_schema_version`
- `guardrail_rules_version`
- `embedding_model_version`
- effective output contract or `output_format`
- `detail_level`
- selected estimation mode or operation type when it changes output semantics
- relevant structured request parameters that materially change the answer:
  - project type
  - industry/domain when present
  - delivery urgency
  - delivery approach
  - hosting constraints
  - integrations/categories
  - data sensitivity
  - UI languages
  - preprocessing mode
  - any future tenant/product policy that changes estimation assumptions

The bucket should be strict enough to avoid comparing materially different jobs and stable enough to create useful reuse.

### Vector Component

Compute the embedding from normalized free-text surfaces only, for example:

- project summary or description
- user-provided problem statement
- deliverables
- out-of-scope notes
- constraints written as free text
- external dependency notes
- current canonical `assessment_surface` when it is the most faithful free-text representation

Do not rely on embeddings to distinguish structured fields that are critical for product behavior. Put those fields in the deterministic bucket.

### Stored Entry Shape

The stored artifact should be versioned and sufficient to reconstruct the response without another LLM call:

```json
{
  "cache_schema_version": "1",
  "bucket": "semantic:estimation:v1:<hash>",
  "bucket_hash": "<hash>",
  "input_fingerprint": "<hash of normalized free-text surface>",
  "embedding_model": "text-embedding-3-small",
  "embedding_model_version": "text-embedding-3-small:YYYY-MM-DD-or-config-version",
  "prompt_version": "v1",
  "examples_version": "v1",
  "output_schema_version": "1",
  "guardrail_rules_version": "registry-default",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "mode": "standard",
  "result": { "..." : "EstimationResult JSON" },
  "finish_reason": "stop",
  "created_at": "2026-05-14T15:00:00Z",
  "expires_at": "2026-05-15T15:00:00Z",
  "safe_to_cache": true,
  "safe_to_display": true
}
```

Do not store raw secrets, full prompts with sensitive content, provider credentials, or unbounded payloads.

## Data Model Changes

Add internal Pydantic models or dataclasses for semantic cache contracts:

- `SemanticCacheConfig`
- `SemanticCacheBucket`
- `SemanticCacheLookupRequest`
- `SemanticCacheEntry`
- `SemanticCacheWriteRequest`
- `CacheDecision`
- `CacheLookupResult`
- `CacheMissReason`
- `CacheWriteDecision`
- `CachedEstimationArtifact`

Recommended enums:

- `CacheDecisionStatus`: `disabled`, `log_only`, `hit`, `miss`, `error`
- `CacheMissReason`: `disabled`, `log_only`, `bucket_empty`, `no_neighbor`, `low_score`, `payload_invalid`, `guardrail_not_cacheable`, `store_error`, `embedding_error`

The cached response must be revalidated against current Pydantic models on read. If validation fails, treat the entry as a miss and emit an observability event.

## API Changes

Extend the v2 `EstimationResponse` with cache metadata. Preferred public contract:

```json
{
  "cached": false,
  "cache_score": null,
  "cache_bucket": null,
  "cache_miss_reason": "no_neighbor",
  "prompt_version": "v1",
  "request_id": "est_abc123"
}
```

Fields:

- `cached: bool`
- `cache_score: float | null`
- `cache_bucket: str | null`
- `cache_miss_reason: str | null`
- `prompt_version: str`
- `request_id: str | null`
- Optional later: `cache_age_seconds: int | null`, `cache_mode: "disabled" | "log_only" | "enabled"`

Do not expose raw Redis keys, vector ids, raw embeddings, raw prompts, or unredacted candidate input.

Frontend guidance:

- The frontend may use `cached` for UX and telemetry.
- The frontend must not implement cache lookup, thresholding, embedding generation, or bucket construction.

## Configuration

Add typed settings in `app/config.py` and document them in `.env.example`, `README.md`, and `docs/technical/README.md`.

Recommended variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SEMANTIC_CACHE_ENABLED` | `false` | Master flag for serving semantic hits. |
| `SEMANTIC_CACHE_LOG_ONLY` | `true` | Runs embedding and lookup but never bypasses the LLM. |
| `SEMANTIC_CACHE_REDIS_URL` | empty | Redis DSN for vector cache when enabled/log-only. |
| `SEMANTIC_CACHE_NAMESPACE` | `semantic:estimation` | Prefix for index and keys. |
| `SEMANTIC_CACHE_TTL_SECONDS` | `86400` | Default expiration for validated entries. |
| `SEMANTIC_CACHE_SIMILARITY_THRESHOLD` | `0.92` | Minimum score for serving hits. |
| `SEMANTIC_CACHE_MAX_CANDIDATES` | `5` | Number of nearest candidates retrieved for diagnostics and tie-breaking. |
| `SEMANTIC_CACHE_EMBEDDING_PROVIDER` | `openai` | Embedding provider behind the adapter. |
| `SEMANTIC_CACHE_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model id. |
| `SEMANTIC_CACHE_EMBEDDING_TIMEOUT_SECONDS` | `10` | Timeout for embedding calls. |
| `SEMANTIC_CACHE_MAX_PAYLOAD_BYTES` | `262144` | Maximum serialized cache entry size. |
| `SEMANTIC_CACHE_ENABLED_ENDPOINTS` | `api_v2_estimate` | Comma-separated endpoint/operation allowlist. |
| `SEMANTIC_CACHE_ENABLED_TENANTS` | empty | Optional tenant allowlist; empty means use global rollout rules. |
| `SEMANTIC_CACHE_ENABLED_OPERATIONS` | `estimation_v2` | Optional operation allowlist. |

If `SEMANTIC_CACHE_ENABLED=false` and `SEMANTIC_CACHE_LOG_ONLY=false`, the app should avoid Redis and embedding provider calls.

## Module and Class Naming Proposal

Use clear boundaries that map onto domain/application/infrastructure while fitting the current `app/` layout.

### Domain / Contracts

- `app/services/semantic_cache/contracts.py`
- `SemanticCacheEntry`
- `SemanticCacheLookupRequest`
- `CacheLookupResult`
- `CacheDecision`
- `CacheMissReason`
- `CachedEstimationArtifact`

### Application / Orchestration

- `app/services/semantic_cache/service.py`
- `SemanticCacheService`
- `InferenceOrchestrator` or current `LLMPipeline` integration point
- `CacheBucketBuilder`
- `SemanticCachePolicy`

### Infrastructure / Adapters

- `app/services/semantic_cache/embeddings.py`
- `EmbeddingProvider`
- `OpenAIEmbeddingProvider`
- `app/services/semantic_cache/repository.py`
- `SemanticCacheRepository`
- `RedisSemanticCacheRepository`
- `app/services/semantic_cache/redis_index.py`
- `RedisSemanticCacheIndexManager`

Avoid Redis-specific imports outside the infrastructure adapter.

## Infrastructure Stack

Initial stack:

- Redis as cache and vector search engine.
- `redisvl` or equivalent Redis vector-search helper.
- `redis` Python client for lower-level operations where needed.
- OpenAI embeddings by default through an `EmbeddingProvider` interface.

Future-compatible alternatives:

- `pgvector` for Postgres-centered deployments.
- Qdrant for dedicated vector search.
- Pinecone for managed vector infrastructure.

The application layer should not change if the repository adapter changes.

## Rollout Strategy

### Phase 0: Implementation behind flags

- Add settings, contracts, bucket builder, embedding adapter interface, repository interface, and fake implementations for tests.
- Default to disabled in local/prod unless explicitly configured.

### Phase 1: Log-only / shadow mode

- Compute bucket and embedding.
- Lookup top candidates.
- Log top-1 score, bucket, would-hit decision, miss reason, and threshold.
- Continue to call the LLM every time.
- Write only validated safe responses so future lookups have realistic data.

### Phase 2: Threshold calibration

- Analyze log-only data:
  - top-1 score distribution
  - potential hit rate by threshold
  - candidate agreement with fresh LLM output
  - manually reviewed false positives
  - buckets with suspiciously broad matches
- Choose a conservative initial threshold and document why.

### Phase 3: Canary serving

- Enable serving for one endpoint, tenant, operation, or internal environment.
- Keep kill switch available.
- Monitor quality and latency before wider rollout.

### Phase 4: Gradual rollout

- Expand by endpoint, tenant, or operation family.
- Keep log-only enabled for new buckets or new prompt/embedding versions.
- Recalibrate after significant prompt, schema, guardrail, or embedding model changes.

### Phase 5: General availability

- Make semantic cache an operational feature with dashboards, alerts, documented rollback, and periodic threshold review.

## Observability and Analytics

Emit structured logs and metrics without raw user text, raw prompts, secrets, or embeddings.

Required events:

- `semantic_cache.disabled`
- `semantic_cache.lookup_started`
- `semantic_cache.lookup_completed`
- `semantic_cache.hit`
- `semantic_cache.miss`
- `semantic_cache.log_only_candidate`
- `semantic_cache.write_skipped`
- `semantic_cache.write_completed`
- `semantic_cache.validation_failed_on_read`
- `semantic_cache.error`

Required fields where applicable:

- `request_id`
- `trace_id`
- `operation`
- `tenant_id_hash` if tenants exist
- `bucket`
- `prompt_version`
- `output_schema_version`
- `guardrail_rules_version`
- `embedding_model`
- `threshold`
- `top_score`
- `candidate_count`
- `decision`
- `miss_reason`
- `cached`
- `latency_ms_embedding`
- `latency_ms_lookup`
- `latency_ms_saved_estimate`
- `estimated_cost_saved_usd`

Required metrics:

- Real hit rate.
- Potential hit rate in log-only.
- Score distribution.
- False positives detected by review or downstream signal.
- Estimated latency saved.
- Estimated cost saved.
- Request count by bucket.
- Miss ratio caused by high threshold.
- Possible collision ratio caused by broad buckets.
- Cache write count and write-skip reasons.
- Cache read validation failure count.
- Embedding latency and error rate.
- Redis/vector lookup latency and error rate.

If OpenTelemetry and Prometheus are available, expose metrics through the existing observability path. If not, define stable log events first and add metrics as a follow-up.

## Security and Quality Requirements

- Never serve a cache hit before input guardrails pass.
- Never write unvalidated responses.
- Never cache errors, provider timeouts, partial responses, degraded responses, blocked outputs, or unsafe outputs.
- Never cache payloads larger than `SEMANTIC_CACHE_MAX_PAYLOAD_BYTES`.
- Never log raw embeddings, secrets, API keys, full prompts, or sensitive user text.
- Protect against cache poisoning by requiring:
  - strict output validation,
  - output guardrail success,
  - cache schema versioning,
  - TTL,
  - read-time validation,
  - tenant/workspace isolation when applicable.
- Treat cache store failures as miss unless the failure indicates unsafe state.
- Use fail-closed behavior for invalid cached artifacts.
- Use stable serialization and explicit cache schema version.
- Keep TTL configurable per use case or operation when needed.

## Risks

- False positives can return plausible but wrong estimates.
- Poor bucket design can compare materially different requests.
- Threshold tuned only on synthetic tests may fail in production traffic.
- Embedding model changes can alter score distributions.
- Cache poisoning can amplify a bad response.
- Payload drift can break read-time validation after schema changes.
- Redis/vector search latency can offset savings on cache misses.
- Cross-tenant reuse can leak information if tenant isolation is not explicit.
- Log-only can create misleading confidence if false positives are not reviewed.

Mitigations:

- Conservative threshold.
- Strict bucket fields.
- Prompt/schema/guardrail/embedding version in bucket or namespace.
- Log-only before serving.
- Human review sample for candidate hits.
- Short initial TTL.
- Read-time validation and fail-closed miss.
- Kill switch.

## Success Metrics

Primary:

- Real semantic cache hit rate after rollout.
- p50/p95 latency reduction for served hits.
- Estimated LLM cost reduction per 1,000 requests.
- False-positive rate below agreed product threshold.

Secondary:

- Potential hit rate in log-only.
- Score distribution stability by bucket.
- Cache read validation failure rate near zero.
- No increase in guardrail failures or user-visible degraded responses.
- No increase in regenerate/retry actions from users for cached responses.

North-star metric:

```text
effective_cache_value = hit_rate * (1 - quality_regression_rate)
```

Hit rate alone is not sufficient.

## Acceptance Criteria

- [ ] Input guardrails always run before embedding and cache lookup.
- [ ] A request with the same intent, same bucket, and score above threshold returns `cached=true`.
- [ ] A request with the same meaning but different `output_format` does not collide.
- [ ] A request with the same meaning but different `detail_level` does not collide when detail level changes output expectations.
- [ ] Changing `prompt_version` prevents reuse of old entries.
- [ ] Old prompt-version buckets expire by TTL without manual invalidation.
- [ ] A response that fails output Pydantic validation is not persisted.
- [ ] A response that fails output semantic guardrails is not persisted.
- [ ] Errors, timeouts, degraded responses, and partial responses are never cached.
- [ ] Log-only mode never bypasses the LLM, even when a candidate exceeds threshold.
- [ ] Log-only mode emits top-1 score, bucket, suggested decision, and miss/hit reason.
- [ ] Cache disabled mode performs no embedding or Redis calls.
- [ ] Read-time validation failure is treated as miss and logged.
- [ ] The response includes `cached`, `cache_score`, `cache_bucket`, `prompt_version`, and `request_id`.
- [ ] Miss reason is exposed when safe and useful: `no_neighbor`, `low_score`, `disabled`, `log_only`, or `bucket_empty`.
- [ ] Metrics/logs include score and bucket without raw user text or embeddings.
- [ ] Redis outage does not break estimation; it degrades to normal LLM flow.
- [ ] Tenant/operation allowlists can restrict rollout when configured.

## Test Plan

### Unit Tests

- Bucket determinism: same structured input yields same bucket.
- Bucket isolation: changes to `prompt_version`, `output_format`, `detail_level`, operation, schema version, guardrail rules version, tenant, or embedding model version change bucket/namespace as expected.
- Vector surface construction includes free-text fields and excludes structural fields already represented in the bucket.
- Threshold policy: scores below threshold miss; scores equal/above threshold hit.
- `CacheMissReason` mapping for disabled, log-only, empty bucket, no neighbor, low score, invalid payload, and store error.
- Serialization round-trip for cached artifact.
- Payload size limit rejects oversized entries.
- Read-time validation converts invalid cached payload to miss.
- Disabled config avoids embedding and repository calls.

### Pipeline Tests

- Input guardrails execute before semantic cache lookup.
- Cache hit bypasses provider call only when enabled and not log-only.
- Cache miss calls LLM and writes only after output validation and guardrails.
- Log-only lookup still calls LLM.
- Output guardrail degradation skips cache write.
- Provider errors skip cache write.
- `safe_to_cache=False` skips cache write.
- `prompt_version` isolation prevents reuse across prompt versions.
- TTL-expired entry behaves as miss.

### Integration Tests

- Use fake or mocked `SemanticCacheRepository`; use fakeredis or testcontainers only if the project explicitly accepts that dependency.
- First request writes validated cache entry; second semantically equivalent request in same bucket hits.
- Semantically similar but materially different requests do not hit when bucket differs.
- Top candidate below threshold logs low-score miss.
- Redis/repository error path returns normal LLM response.
- Response metadata is present and stable in API tests.

### Regression Test Dataset

Create curated pairs:

- Same intent, different wording: should hit.
- Same wording pattern, different material constraint: should miss.
- Same project, different output format: should miss.
- Same project, different prompt version: should miss.
- Similar product but different tenant/workspace when multitenancy exists: should miss.
- Malicious input similar to valid cached input: input guardrails block before lookup.

### Manual Checks

- Run local API with semantic cache disabled and confirm baseline behavior.
- Run with log-only and confirm LLM is still called.
- Run with enabled cache and a fake or local Redis vector index.
- Send two semantically equivalent requests and confirm second response reports `cached=true`.
- Change `PROMPT_ESTIMATION_VERSION` and confirm miss.

Recommended commands after implementation:

```bash
uv run pytest
uv run pytest tests/guardrails tests/services
uv run uvicorn app.main:app --reload
```

## Implementation plan (agent, 2026-05-14)

Numbered baby-steps (one reviewer-friendly commit each where practical). TDD: failing test first for logic; verification with `uv run pytest` scoped to the touched files, then broader suite before merge.

| Step | Goal | TDD / verification |
|------|------|--------------------|
| 1 | Typed `Settings` + `.env.example` + Pydantic contracts (`CacheMissReason`, lookup/write/decision models) | `tests/test_semantic_cache_settings.py`, `tests/test_semantic_cache_contracts.py` |
| 2 | `CacheBucketBuilder`: canonical JSON + SHA-256 bucket hash; vector text surface from free-text fields | `tests/test_semantic_cache_bucket.py` |
| 3 | `EmbeddingProvider` + `FakeEmbeddingProvider` (deterministic unit vector); no calls when cache fully off | `tests/test_semantic_cache_embeddings.py` |
| 4 | `SemanticCacheRepository` protocol + `InMemorySemanticCacheRepository` + `NullSemanticCacheRepository` | `tests/test_semantic_cache_repository.py` |
| 5 | `SemanticCacheService`: disabled / log-only / threshold / write policy + cosine nearest-neighbor in bucket | `tests/test_semantic_cache_service.py` |
| 6 | `LLMPipeline`: after input guardrails → lookup; serve hit only when enabled and not log-only; write after safe output; `prepare_structured_prelude` on service | `tests/test_llm_pipeline.py` + new cases |
| 7 | `EstimationResponse` + `assemble_estimation_v2_response` + router: `cached`, `cache_score`, `cache_bucket`, `cache_miss_reason` | API / schema tests |
| 8 | Structured logs (`semantic_cache.*`), `README.md` + `docs/technical/README.md` | Log smoke via unit tests where practical |

**Open WIP note:** Redis + `redisvl` vector index adapter is deferred behind the repository interface; this PR ships in-memory + null backends and optional `SEMANTIC_CACHE_USE_MEMORY_STORE` for local calibration without Redis.

**Open WIP PR:** https://github.com/povedica/master-ia-lidr/pull/6

## Implementation progress

- [x] Step 1: Settings and contracts
- [x] Step 2: Bucket builder
- [x] Step 3: Embedding boundary
- [x] Step 4: Repository adapters
- [x] Step 5: Semantic cache service
- [x] Step 6: `LLMPipeline` integration
- [x] Step 7: API response metadata
- [x] Step 8: Observability and documentation

## Implementation Tasks

### Task 1: Define contracts and settings

- Add semantic cache settings to `Settings`.
- Add `.env.example` documentation.
- Add Pydantic/dataclass contracts for lookup, entries, decisions, and miss reasons.
- Add tests for settings defaults and validation.

### Task 2: Build deterministic bucket logic

- Implement `CacheBucketBuilder`.
- Define canonical JSON serialization and hashing.
- Include prompt, schema, guardrail, embedding, operation, and structured request fields.
- Add unit tests for determinism and isolation.

### Task 3: Build embedding adapter boundary

- Define `EmbeddingProvider`.
- Implement first provider adapter behind config.
- Add timeout/error handling.
- Add fake provider for tests.
- Ensure no embedding calls happen when cache is fully disabled.

### Task 4: Build semantic cache repository boundary

- Define `SemanticCacheRepository`.
- Implement Redis vector repository using `redisvl` or equivalent.
- Add index initialization or migration strategy.
- Add TTL and namespace handling.
- Add fake repository tests.

### Task 5: Build `SemanticCacheService`

- Combine bucket construction, embedding, lookup, threshold policy, log-only behavior, and write decisions.
- Return `CacheDecision` / `CacheLookupResult`.
- Add unit tests for hit, miss, disabled, log-only, and error paths.

### Task 6: Integrate into `LLMPipeline`

- Insert lookup after input guardrails.
- Serve cached response only on valid enabled hit.
- Write after output validation and guardrails.
- Preserve existing error/degraded behavior.
- Add pipeline tests for ordering and safety.

### Task 7: Extend API response metadata

- Add `cached`, `cache_score`, `cache_bucket`, and `cache_miss_reason` or an equivalent stable cache metadata object.
- Ensure public fields do not expose raw keys or sensitive payload.
- Add API response tests.

### Task 8: Add observability

- Add structured logs and metrics hooks.
- Include hit rate, potential hit rate, score distribution, miss reasons, and cost/latency estimates.
- Add tests for event emission where practical.

### Task 9: Documentation and rollout notes

- Update `README.md`, `.env.example`, and `docs/technical/README.md`.
- Document log-only calibration procedure.
- Document rollback and kill switch.
- Document threshold calibration expectations.

### Task 10: Calibration artifact

- Capture or define a small reviewed dataset of semantically equivalent and materially different request pairs.
- Record initial threshold recommendation and review criteria.
- Keep this artifact outside runtime code; it can live under docs or test fixtures depending on final use.

## Dependencies

Runtime candidate dependencies:

- `redis`
- `redisvl` or equivalent Redis vector search helper
- provider SDK already used for embeddings, or an additional embedding client if needed

Development/testing candidate dependencies:

- `fakeredis` only if it supports the needed behavior and does not create false confidence for vector search
- otherwise, prefer fake repository interfaces for deterministic tests

External dependencies:

- Redis instance with vector search support.
- Embedding provider credentials when live embedding calls are enabled.
- Observability backend if Prometheus/OpenTelemetry metrics are enabled.

## Documentation Plan

- Update `.env.example` with all semantic cache variables.
- Update `README.md` configuration section.
- Update `docs/technical/README.md` with:
  - pipeline order,
  - semantic cache architecture,
  - log-only rollout,
  - response metadata,
  - Redis/vector search requirement,
  - security constraints.
- If mirrored Second Brain docs are maintained, sync via:

```bash
bash scripts/sync-estimador-cag-docs.sh
```

## Open Questions

- What is the initial precision target for semantic hits before serving is enabled?
- Which request fields are truly structural product constraints and must be in the bucket from day one?
- Is tenant/workspace identity already available in the API layer, or should the first version use an explicit `"default"` tenant bucket?
- Should embedding model version be part of the bucket or namespace? Recommended: namespace when changing the embedding space.
- Should cached responses include usage tokens from the original LLM call, omit usage, or mark usage as cached/non-billable?
- Should clients be able to request cache bypass for debugging or user-triggered regeneration?
- What is the maximum acceptable embedding+lookup latency on miss?
- Should Redis index initialization happen at app startup, lazily on first use, or through an operational migration command?
- Do we need per-operation TTLs from the first release, or is one conservative TTL enough?
- How will false positives be reviewed during log-only calibration?

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
| `d8138a4` | `docs(work-items): add feature-013 semantic cache layer spec` | Add canonical work item for semantic cache (bucket + vector, log-only rollout, API metadata, tests, security). |
| `a8003d4` | `docs(work-items): fix feature-013 repository commit log short hash` | Align the commits table short hash with the amended spec commit. |
| `28a7bab` | `feat(semantic-cache): add guarded semantic cache for v2 estimation` | Settings, contracts, bucket, embeddings, in-memory repo, pipeline integration, API metadata, tests, docs; work item plan/progress; Redis/redisvl adapter deferred. |
