# Estimador CAG — Technical documentation

This document is the living technical baseline for the `estimador-cag` project. It extends the subproject `README.md` with architecture, stack, configuration, runtime flow, logging, testing, and evolution guidelines.

**Language:** all content under `docs/technical/` is written in **English** (prose, headings, and tables). Code paths, commands, and identifiers stay as in the repository.

The goal is documentation that supports development, debugging, and growth without losing the simplicity of the first version.

## Table of contents

- [1. Overview](#1-overview)
- [2. Technical stack](#2-technical-stack)
- [3. Libraries and frameworks](#3-libraries-and-frameworks)
- [4. Local setup](#4-local-setup)
- [5. Environment variables](#5-environment-variables)
- [6. Scripts and commands](#6-scripts-and-commands)
- [7. Directory layout](#7-directory-layout)
- [8. Technical architecture](#8-technical-architecture)
- [9. Estimation request flow](#9-estimation-request-flow)
- [10. CAG design](#10-cag-design)
- [11. API contract](#11-api-contract)
- [12. Response metadata](#12-response-metadata)
- [13. Logging](#13-logging)
- [14. Error handling](#14-error-handling)
- [15. Testing and validation](#15-testing-and-validation)
- [16. API collection](#16-api-collection)
- [17. Documentation and sync](#17-documentation-and-sync)
- [18. Security and secrets](#18-security-and-secrets)
- [19. Evolution guide](#19-evolution-guide)
- [20. Troubleshooting](#20-troubleshooting)
- [21. Embedding pipeline (Session 07)](#21-embedding-pipeline-session-07)
- [22. Postgres pgvector baseline (feature-036)](#22-postgres-pgvector-baseline-feature-036)
- [23. Semantic search endpoint (feature-038)](#23-semantic-search-endpoint-feature-038)
- [24. Worktree task orchestrator](#24-worktree-task-orchestrator)
- [CAG stress testing](./cag-stress-testing.md) — feature-029 instrumentation, runner, metrics (standalone reference)

## 1. Overview

`estimador-cag` is a FastAPI service that accepts a client meeting transcription and returns a structured software estimate.

The project uses **Context-Augmented Generation (CAG)** in a deliberately small form:

- Few-shot reference text lives under `app/context/examples/*.txt` as a flat pool; `app/context/examples.py` returns a **random subset** (2–4 examples) per request. Tests seed RNG where non-determinism would break assertions.
- The app builds a `system prompt` with Jinja2 instructions and prior examples.
- The live transcription or guided-form brief is sent as the `user` message.
- Depth and layout preferences come from guided-form fields (`detail_level`, `output_format`) when present.
- A provider chain (`openai,anthropic` by default) returns an estimate with assumptions, a task/hours table, and delivery notes.

The baseline does not include authentication, a frontend, or production deployment. **Optional** filesystem persistence of successful `200` responses exists behind `ESTIMATION_OUTPUT_PERSIST_ENABLED` (see §5 and §14). It is an AI Engineering baseline meant for learning and safe iteration.

## 2. Technical stack

| Area | Current choice | Rationale |
|------|----------------|-----------|
| Language | Python `>=3.11,<3.12` | Controlled compatibility and modern typing. |
| Package manager | `uv` | Reproducible environment, fast installs, lockfile. |
| HTTP framework | FastAPI | Typed API, automatic OpenAPI, Pydantic integration. |
| ASGI server | `uvicorn[standard]` | Local runtime for FastAPI. |
| Configuration | `pydantic-settings` | Typed settings from environment and `.env`. |
| LLM providers | OpenAI + Anthropic + static fallback | Ordered chain with graceful fallback and explicit degraded mode. |
| Default model | `gpt-4o-mini` | Low cost for exercises and manual checks. |
| Tests | `pytest`, `pytest-asyncio`, `httpx` | Fast, deterministic suite without real provider calls. |
| Persistence (semantic search) | Postgres 16 + pgvector, SQLAlchemy async, Alembic | Schema baseline for `documents` / `chunks`; ingest HTTP still in-memory until feature-037. |
| Manual API client | OpenCollection/Bruno collection under `api-collection/` | Versioned manual checks alongside the code. |

## 3. Libraries and frameworks

Runtime dependencies declared in `pyproject.toml`:

- `fastapi[standard]`: web framework, validation, OpenAPI docs.
- `uvicorn[standard]`: local ASGI server.
- `pydantic-settings`: typed configuration from the environment.
- `openai`: official SDK for OpenAI.
- `anthropic`: official SDK for Anthropic.
- `python-dotenv`: load `.env` in local development.
- `redis`: async Redis client used by the optional Redis Stack / RediSearch semantic cache adapter.
- `sqlalchemy`, `asyncpg`, `greenlet`: async ORM and Postgres driver for semantic-search persistence.
- `pgvector`: SQLAlchemy integration for `vector` columns (`Vector(1536)` aligned with `text-embedding-3-small`).
- `alembic`: versioned async migrations (`alembic/`, `DATABASE_URL` from settings).

Development dependencies:

- `pytest`: test runner.
- `pytest-asyncio`: async test support.
- `httpx`: HTTP client used by FastAPI `TestClient` and tests.

Important rule: tests mock provider SDK clients. The default suite must not depend on real provider API keys.

## 4. Local setup

Requirements:

- Python 3.11.
- `uv` on the host.
- Docker (optional but recommended) for Redis Stack, Postgres pgvector, and the full Compose stack.
- At least one provider key (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY`) if you want live model estimates.

From the repository root:

```bash
uv sync --group dev
cp .env.example .env
```

**Full stack (API + web + Redis + Postgres):**

```bash
docker compose up --build
```

**Postgres only** (migrations / schema inspection without starting the API):

```bash
docker compose up -d postgres
```

Then edit `.env` locally:

```text
OPENAI_API_KEY=...
# and/or
ANTHROPIC_API_KEY=...
```

Never commit `.env`.

Run the API locally:

```bash
uv run uvicorn app.main:app --reload
```

Useful URLs:

- `GET http://127.0.0.1:8000/`
- `GET http://127.0.0.1:8000/health`
- `POST http://127.0.0.1:8000/api/v1/estimate`
- `http://127.0.0.1:8000/docs`

## 5. Environment variables

Variables documented in `.env.example`:

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `LLM_PROVIDERS` | Yes | `openai,anthropic` | Ordered provider chain used for fallback. |
| `STATIC_FALLBACK_ENABLED` | No | `true` | Appends deterministic local fallback provider at chain end. |
| `LLM_AUTH_FALLBACK` | No | `false` | If `true`, provider auth/config errors may continue to the next provider. |
| `LLM_DOMAIN_GUARDRAIL_ENABLED` | No | `true` | Enables service-level rejection for out-of-domain prompts before provider calls. |
| `OPENAI_API_KEY` | Yes for OpenAI live calls | empty | OpenAI credential. Must not appear in logs, tests, or documentation. |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | Model used by the service. |
| `OPENAI_TIMEOUT_SECONDS` | No | `30` | OpenAI client timeout. |
| `ANTHROPIC_API_KEY` | Yes for Anthropic live calls | empty | Anthropic credential for fallback or primary usage. |
| `ANTHROPIC_MODEL` | No | `claude-3-5-haiku-latest` | Anthropic model used by the service. |
| `ANTHROPIC_TIMEOUT_SECONDS` | No | `30` | Anthropic client timeout. |
| `ANTHROPIC_MAX_TOKENS` | No | `2048` | Max output tokens for Anthropic generations. |
| `APP_ENV` | No | `local` | Logical runtime environment. Logged at startup. |
| `DEV_MODE` | No | `false` | When `true`, responses include `prompt_version`, `examples_version`, timing, optional `usage`, and approximate `estimated_cost_usd` when usage is available. |
| `ESTIMATION_OUTPUT_TOKENS_MAX` | No | `2048` | Max completion output tokens for estimation provider calls. |
| `ESTIMATION_OUTPUT_PERSIST_ENABLED` | No | `false` | When `true`, successful `200` responses persist the `estimation` string to `output-responses/response-YYYYmmdd-hhmmss.md` (UTC). Persistence failure returns `503`. |
| `LLM_CALL_PERSIST_ENABLED` | No | `false` | When `true`, each successful LLM provider call persists request + response JSON to `output-responses/llm-call-YYYYmmdd-HHMMSS-NNN.json` (UTC). Best-effort; failures do not affect API responses. |
| `LOG_LEVEL` | No | `INFO` | Base logging level. |
| `SEMANTIC_CACHE_ENABLED` | No | `false` | Allows serving validated semantic cache hits when the store and rollout allow it. |
| `SEMANTIC_CACHE_LOG_ONLY` | No | `true` | Runs semantic cache diagnostics without bypassing the LLM. |
| `SEMANTIC_CACHE_REDIS_URL` | No | empty | Redis Stack DSN for RediSearch vector storage when memory store is off. |
| `SEMANTIC_CACHE_USE_MEMORY_STORE` | No | `false` | Uses the single-process in-memory repository for local experiments/tests. |
| `SEMANTIC_CACHE_SIMILARITY_THRESHOLD` | No | `0.92` | Minimum similarity score for serving a cached response. |
| `EMBEDDING_PIPELINE_MODEL` | No | `text-embedding-3-small` | Embedding model for the Session 07 ingest pipeline. |
| `EMBEDDING_PIPELINE_BATCH_SIZE` | No | `100` | Chunks per OpenAI embeddings request in `embed_many`. |
| `DATABASE_URL` | No | empty | Async Postgres DSN (`postgresql+asyncpg://user:pass@host:5432/db`). Required for Alembic and future persisted ingest. Compose sets this on the `app` service automatically. |

Loading is centralized in `app/config.py` via `Settings`, with `.env` as a local source and `extra="ignore"` so unknown variables do not break startup.

## 6. Scripts and commands

Main subproject commands:

```bash
uv sync --group dev
uv run uvicorn app.main:app --reload
uv run pytest
```

**Postgres + Alembic (feature-036):**

```bash
docker compose up -d postgres
docker compose exec postgres psql -U estimator -d estimator -c "SELECT version();"

export DATABASE_URL=postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator
uv run alembic upgrade head
uv run alembic current
# Roll back on a dev database:
uv run alembic downgrade base
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Sample estimate request:

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/estimate \
  -H "Content-Type: application/json" \
  -d '{"transcription":"The client needs a REST API for orders with idempotent POST."}'
```

Documentation mirror sync from the repository root:

```bash
bash scripts/sync-estimador-cag-docs.sh
```

That script mirrors canonical notes from `second-brain-master-ia/proyectos/estimador-cag/` into `proyectos/estimador-cag/docs/`.

## 7. Directory layout

Current subproject layout:

```text
proyectos/estimador-cag/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── context/
│   │   ├── __init__.py
│   │   ├── examples.py
│   │   ├── examples/
│   │   │   └── sample-*.txt
│   ├── routers/
│   │   ├── __init__.py
│   │   └── estimations.py
│   └── services/
│       ├── __init__.py
│       ├── domain_guardrails.py
│       ├── llm_service.py
│       └── response_output_writer.py
├── api-collection/
│   └── Estimador CAG/
├── docs/
│   ├── README.md
│   ├── sesiones/
│   ├── work-items/
│   └── technical/
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_config.py
│   ├── test_examples.py
│   ├── test_prompt_loader.py
│   ├── test_llm_service.py
│   └── test_response_output_writer.py
├── output-responses/
├── .env.example
├── .gitignore
├── pyproject.toml
├── README.md
└── uv.lock
```

Responsibilities:

| Path | Responsibility |
|------|------------------|
| `app/main.py` | FastAPI composition root: logging setup, lifespan, routers, base endpoints. |
| `app/config.py` | Typed settings from the environment. |
| `app/routers/estimations.py` | HTTP boundary: Pydantic schemas, validation, response metadata, HTTP errors. |
| `app/services/domain_guardrails.py` | Deterministic domain filter to reject non-estimation prompts before provider calls. |
| `app/services/llm_service.py` | CAG logic, prompt construction, provider-chain orchestration, fallback policy. |
| `app/prompts/estimation/v2/partials/system_instructions.md.j2` | Unified system preamble (uses `detail_level` / `output_format` from guided form). |
| `app/services/providers/` | Provider implementations (`openai`, `anthropic`, `static_fallback`) and chain registry. |
| `app/context/examples.py` | Loads few-shot pool from `app/context/examples/*.txt` and returns a random subset per request. |
| `app/services/response_output_writer.py` | Optional persistence of successful `estimation` text to `output-responses/`. |
| `app/services/llm_call_persistence.py` | Optional JSON persistence of LLM request/response pairs to `output-responses/`. |
| `app/database.py` | Async SQLAlchemy engine/session setup for Postgres (feature-036). |
| `app/models/` | ORM tables `documents` and `chunks` with pgvector embeddings column. |
| `alembic/` | Async Alembic migrations; initial schema in `versions/0001_initial_schema.py`. |
| `tests/` | Unit and API tests with a mocked provider. |
| `tests/test_database_models.py` | ORM metadata contract tests (no live DB). |
| `api-collection/` | Manual endpoint collection and local environment. |
| `docs/` | Versioned mirror of Second Brain notes, sessions, work items, and technical docs. |

## 8. Technical architecture

The architecture is small and layered. Each layer has a clear boundary:

```mermaid
flowchart TD
    Client[Client / curl / API collection] --> FastAPI[FastAPI app]
    FastAPI --> Router[app.routers.estimations]
    Router --> Settings[app.config.Settings]
    Router --> Service[app.services.EstimationService]
    Service --> Examples[app.context.examples]
    Service --> Chain[Provider chain]
    Chain --> OpenAI[OpenAI API]
    Chain --> Anthropic[Anthropic API]
    Chain --> StaticFallback[Static fallback]
    Router --> Response[EstimateResponse]
```

Current principles:

- `app/main.py` does not contain business logic.
- The router orchestrates HTTP, validation, and metadata.
- SDK-specific behavior is isolated in `app/services/providers/`.
- CAG examples live outside the router and service so they can be versioned and tested.
- Configuration is injected with `Depends(get_settings)` at the HTTP boundary.

## 9. Estimation request flow

```mermaid
sequenceDiagram
    participant Client
    participant Router as estimations.py
    participant Service as llm_service.py
    participant Context as examples.py
    participant Chain as provider_chain
    participant OpenAI
    participant Anthropic
    participant Static as static_fallback

    Client->>Router: POST /api/v1/estimate { transcription }
    Router->>Router: Validate EstimateRequest
    Router->>Service: estimate(transcription)
    Service->>Service: check_estimation_domain (optional)
    Service->>Context: load_examples()
    Context-->>Service: list[EstimationExample]
    Service->>Service: build_system_prompt(examples)
    Service->>Chain: iterate providers by priority
    alt OpenAI succeeds
        Chain->>OpenAI: completion request
        OpenAI-->>Chain: content + usage
    else OpenAI fails transiently
        Chain->>Anthropic: messages request
        Anthropic-->>Chain: content + usage
    else All live providers fail
        Chain->>Static: deterministic fallback
        Static-->>Chain: degraded content
    end
    Chain-->>Service: normalized provider result
    Service-->>Router: EstimationResult
    Router->>Router: build EstimateResponse (full metadata only when DEV_MODE=true)
    Router-->>Client: EstimateResponse
```

Guided-form depth and layout flow into prompt rendering via `detail_level` and `output_format` on `EstimationRequest`.

Recommended effort range shape:

```json
{
  "base_effort_hours": 165,
  "estimated_range": {
    "min": 140,
    "realistic": 180,
    "max": 230
  },
  "confidence": "medium"
}
```

Precision guidance:
"More detailed input enables better scope control, clearer assumptions, lower uncertainty and a more defensible estimation range."

Traceability fields (included in the HTTP response only when `DEV_MODE=true`):

- `request_id`: per-request identifier.
- `timestamp`: UTC response time.
- `latency_ms`: total duration measured in the router.
- `prompt_version`: prompt template version.
- `examples_version`: few-shot pool / sampling contract version.

## 10. CAG design

In this project, CAG means the model receives **team-maintained context** (files under `app/context/examples/` plus prompt files), not data retrieved from a vector database.

Message pattern:

```text
[system]    Instructions + reference estimation examples
[user]      Meeting transcription
[assistant] Generated estimate
```

`build_system_prompt()` includes:

- Unified system instructions from Jinja2 partials under `app/prompts/estimation/` (editable without changing Python code).
- A trailing section `## Reference estimation examples` with few-shot examples from `load_examples()` (sampled from the on-disk pool).

Versioning:

- `PROMPT_VERSION = "v7-guided-input"` in `app/services/llm_service.py` (bump when prompt composition or default prompt-file wording materially changes behavior).
- `EXAMPLES_VERSION = "file-flat-v1-unified-pool"` in `app/services/llm_service.py` (bump when example files, glob pattern, or sampling rules change).

## 11. API contract

### Structured v2 (`POST /api/v2/estimate`)

The guided-form **`EstimationRequest`** is the **inbound** contract for both v1 and v2.

**v2 outbound:** `POST /api/v2/estimate` returns **`EstimationResponse`** with **`result: EstimationResult`** (Pydantic domain model in `app/schemas/estimation_result.py`). The LLM JSON contract is enforced via **Instructor** on top of **LiteLLM** `acompletion` (`app/services/structured_llm_client.py`); schema is derived from the model, not duplicated as hand-written JSON files.

**Prompts:** Markdown + Jinja2 bundles live under `app/prompts/estimation/<version>/`. **`v2` is canonical** (edit files there only). **`v1` is a synced copy** for retrocompat (`scripts/sync-estimation-prompt-v1-from-v2.sh` after `v2/` changes). Default bundle when `PROMPT_ESTIMATION_VERSION` is empty: **`v2`** (`resolve_prompt_bundle_version()` in `app/services/prompt_versions.py`).

| Entry point | Use |
| --- | --- |
| `render_estimation_prompt()` | Full system + user for LLM (`estimation_prompt_rendering.py`) |
| `render_guided_user_message()` | Guided Markdown body (guardrails, cache, tests) |
| `render_assessment_surface()` | Narrow text for domain guardrail (no `##` headers) |

Rendering uses **`StrictUndefined`**, `FileSystemLoader`, `trim_blocks`, and `lstrip_blocks`. Context keys are built in Python (`build_prompt_render_context()` in `prompt_context.py`); templates must not reference raw `EstimationRequest` fields.

The browser UI uses this route with **`Accept: application/json`**; there is **no** v2 SSE surface. (v1 `POST /api/v1/estimate/stream` remains available for Markdown + SSE.)

**Settings:** `STRUCTURED_OUTPUT_MAX_ATTEMPTS` (default `3`), optional `PROMPT_ESTIMATION_VERSION` (`v2` when empty; set `v1` to pin the retrocompat bundle).

### Session simplified submit (`POST /api/v1/sessions/{session_id}/estimate`)

Accepts **`application/json`** or **`multipart/form-data`** (see root `README.md` § Simplified session estimation). Inbound fields map to **`SessionEstimateRequest`** (`app/schemas/simplified_session.py`): `transcript` (min 80 chars), core project fields (optional on follow-up submits when session memory exists), and attachments either as JSON **`AttachmentRef.content_base64`** or repeated multipart field **`attachments`**.

Outbound: **`SessionEstimateResponse`** — top-level `project_metadata` (`DerivedProjectMetadata`), `input_payload`, `warnings`, per-file `attachments` status, and `estimate` (serialized `EstimationResponse` from the v2 assembler).

Orchestration: `session_estimate_request_parser.py` → `SimplifiedSessionEstimationService` (metadata merge, bounded history → `messages_override` on structured LLM) → `LLMPipeline.run_structured`. Session state is in-memory only (`app/services/sessions.py`).

### Embedding ingest (`POST /api/v1/embeddings/ingest`), semantic search (`POST /api/v1/search`), and retrieval debug

Session 07 pipeline routes (isolated from estimator CAG and Redis semantic cache). Full contract: root `README.md` § Embedding pipeline; implementation detail: [§21](#21-embedding-pipeline-session-07), [§23](#23-semantic-search-endpoint-feature-038).

**Ingest:** one `Budget` per request; Postgres transaction; `409` on duplicate `source_path`. **Search:** natural-language `query` + `k`; ranks persisted chunks by pgvector cosine distance (`<=>`); requires `OPENAI_API_KEY` for query embedding. Worked manual analysis (SAML + education query): [feature-038 work item](../work-items/feature-038-semantic-search-endpoint-pgvector.md#manual-query-analysis-verified-on-compose-postgres).

**Retrieval debug:** internal `POST /api/v1/retrieval-debug` returns an explainable branch container. `branches.vector[]` includes rank, chunk/document ids, raw `distance`, and normalized `score = max(0, min(1, 1 - distance))`. `branches.lexical[]` uses Postgres full-text search over `chunks.content`, with branch-local normalized `ts_rank_cd` scores and deterministic `matched_terms`. `final_results[]` adds metadata, excerpt, `source_strategies`, and explanation signals. `GET /api/v1/retrieval-debug/chunks/{chunk_id}` returns full content, neighboring chunks, parent document metadata, embedding model, and optional query distance/similarity. Future hybrid/rerank branches stay `null` with warnings until their feature slices are implemented.

### Semantic cache (v2, optional)

The guarded pipeline in `app/guardrails/llm_pipeline.py` can run a **semantic cache** after input guardrails: deterministic **bucket** hash (prompt, schema, guardrail, and structured request fields) plus **embedding** similarity over free-text surfaces (`app/services/semantic_cache/`). **Serving** hits requires `SEMANTIC_CACHE_ENABLED=true` and a configured store; with `SEMANTIC_CACHE_LOG_ONLY=true` (default), embeddings and lookup run for telemetry but the LLM is **never** skipped. When both `SEMANTIC_CACHE_ENABLED` and `SEMANTIC_CACHE_LOG_ONLY` are `false`, no embedding or store I/O runs. For local experiments without Redis, `SEMANTIC_CACHE_USE_MEMORY_STORE=true` enables an in-process store (single worker only). When `SEMANTIC_CACHE_REDIS_URL` is set and `SEMANTIC_CACHE_USE_MEMORY_STORE=false`, the app uses `RedisSemanticCacheRepository` with Redis Stack / RediSearch vector KNN over entries in the same deterministic bucket.

### `GET /`

Minimal index for humans and browsers:

```json
{
  "service": "Estimador CAG",
  "docs": "/docs",
  "health": "/health",
  "estimate": "POST /api/v1/estimate"
}
```

### `GET /health`

Liveness probe:

```json
{
  "status": "ok"
}
```

### `POST /api/v1/estimate`

Request:

```json
{
  "transcription": "The client needs a REST API for orders with idempotent POST."
}
```

Validation:

- `transcription` is required.
- It must contain at least one character.
- After `strip()`, it must not be empty.
- It must be in the software/project estimation domain.

Response with `DEV_MODE=false` (live provider):

```json
{
  "estimation": "## Estimation: ..."
}
```

Out-of-domain rejection response:

```json
{
  "detail": {
    "code": "out_of_domain",
    "message": "Only software/project estimation requests are supported."
  }
}
```

Degraded response when static fallback is used and `DEV_MODE=false`:

```json
{
  "estimation": "## Estimation: Temporary degraded mode ...",
  "degraded": true
}
```

Response with `DEV_MODE=true`:

```json
{
  "estimation": "## Estimation: ...",
  "model": "gpt-4o-mini",
  "provider": "openai",
  "request_id": "est_abc123def456",
  "timestamp": "2026-04-27T10:00:00Z",
  "latency_ms": 1800,
  "prompt_version": "v7-guided-input",
  "examples_version": "file-flat-v1-unified-pool",
  "usage": {
    "prompt_tokens": 920,
    "completion_tokens": 410,
    "total_tokens": 1330,
    "estimated_cost_usd": 0.000384
  }
}
```

## 12. Response metadata

When `DEV_MODE=false`, the response body is **`estimation` only**, except when static fallback is used, in which case **`degraded: true`** is also included.

When `DEV_MODE=true`, the following are included in addition to `estimation`:

- `request_id`: correlates a response with logs or incident reports.
- `timestamp`: UTC time when the response was produced.
- `latency_ms`: end-to-end request duration from the router.
- `prompt_version`: prompt instruction version.
- `examples_version`: few-shot context version.
- `provider`: provider that produced the response (`openai`, `anthropic`, `static_fallback`).
- `model`: model identifier reported by the provider implementation.
- `degraded`: only present when static fallback is used.
- `usage` (when the provider returns token counts): `prompt_tokens`, `completion_tokens`, `total_tokens`, and optional `estimated_cost_usd` (local approximation from known model pricing).

**Structured v2 (`EstimationResponse`):** when semantic cache is active, responses may include `cached`, `cache_score`, `cache_bucket`, and `cache_miss_reason` (stable string; no raw embeddings or Redis keys).

Cost is not a billing source of truth. It supports learning, tuning, and cost awareness.

## 13. Logging

Base logging is configured in `app/main.py`:

```text
%(levelname)s %(name)s %(message)s
```

The level comes from `LOG_LEVEL`, defaulting to `INFO`.

Current events:

| Event | Level | Source | Safe context |
|-------|-------|--------|----------------|
| `chain_built` | `INFO` | `app.main` | `providers`, `static_fallback_enabled` |
| `app_startup` | `INFO` | `app.main` | `app_env`, `providers` |
| `provider_attempted` | `INFO` | `app.services.llm_service` | `provider`, `model`, `attempt_index` |
| `provider_failed` | `WARNING` / `ERROR` | `app.services.llm_service` | `provider`, `model`, `error_type`, `attempt_index` |
| `provider_succeeded` | `INFO` | `app.services.llm_service` | `provider`, `model` |
| `chain_degraded` | `WARNING` | `app.services.llm_service` | `static_fallback_used` |
| `chain_exhausted` | `WARNING` | `app.services.llm_service` | `providers_tried` |
| `provider_skipped` | `INFO` | `app.services.providers` | `provider`, `reason` |
| `provider_unknown` | `WARNING` | `app.services.providers` | `provider` |
| `estimation_output_persisted` | `INFO` | `app.routers.estimations` | `path` (output file, no secrets) |
| `estimation_output_persist_failed` | `WARNING` | `app.routers.estimations` | Minimal context; no stack trace to clients |
| `semantic_cache.*` | `INFO` / `WARNING` | `app.services.semantic_cache` | `request_id`, bucket display key, scores, thresholds, latencies; no user text or embeddings |
| `retrieval_debug_completed` | `INFO` | `app.routers.retrieval_debug` | `request_id`, `strategies`, `vector_result_count`, `lexical_result_count`, `timings_ms`, `max_results`; no query text, chunk content, embeddings, or secrets |

Rules:

- Do not log `OPENAI_API_KEY`.
- Do not log full prompts by default.
- Do not log full transcriptions when they may contain sensitive information.
- Use stable keys in `extra` for search and correlation.

## 14. Error handling

Input errors:

- FastAPI/Pydantic returns `422` for invalid requests.
- `EstimateRequest` rejects empty `transcription` after trim.

Service errors:

| Case | Outcome |
|------|---------|
| Out-of-domain request (non software/project estimation) | `422 Unprocessable Entity` with `detail.code = "out_of_domain"`; provider chain is not called. |
| Provider timeout / rate limit / unavailable | Next provider in chain is attempted. |
| Provider empty/invalid response | Next provider in chain is attempted. |
| Provider auth/config error | Returns `503` by default (unless `LLM_AUTH_FALLBACK=true`). |
| All providers fail and static fallback enabled | `200` with `provider="static_fallback"` and `degraded=true`. |
| All providers fail and static fallback disabled | `503 Service Unavailable`. |
| Unknown provider name in `LLM_PROVIDERS` | Skipped with `provider_unknown` warning. |
| Output persistence enabled but filesystem write fails | `503` with a safe message; see `estimation_output_persist_failed` log. |

The router maps:

- `DomainGuardrailError` to `422 Unprocessable Entity`
- `EstimationError` to `503 Service Unavailable`

This avoids leaking stack traces or internal details to API clients.

## 15. Testing and validation

Default command (fast suite; **`slow` tests deselected**):

```bash
uv run pytest
```

Heavy tests (eval soft/judge, live LLM smoke) require opt-in:

```bash
uv run pytest --run-heavy -m slow
# or: RUN_HEAVY_TESTS=1 uv run pytest -m slow
```

See `docs/work-items/spec-001-pytest-heavy-test-opt-in.md` and [session-estimation-evals.md](../evals/session-estimation-evals.md).

Current coverage:

- `tests/test_config.py`: settings and environment overrides.
- `tests/test_llm_service.py`: prompt construction, transcription validation, timeout, empty content, mocked success path.
- `tests/test_examples.py`: example pool loading and sampling behavior.
- `tests/test_prompt_loader.py`: unified system instructions partial.
- `tests/test_system_instructions_template.py`: v2 bundle has no `partials/modes/`.
- `tests/test_response_output_writer.py`: output path and UTF-8 write behavior.
- `tests/test_api.py`: root, health, response shape, `DEV_MODE`, validation, `503` mapping, optional output persistence.

Testing rules:

- Do not use real API keys in tests.
- Mock provider SDK clients.
- Mock Redis clients for semantic cache tests; the default suite must not require a live Redis Stack instance.
- Test project-owned logic: prompts, minimal parsing, metadata, errors, settings.
- Keep tests fast and deterministic.
- Mark token-costing or multi-run tests with `@pytest.mark.slow`; they are excluded from default `pytest`.

Minimal manual validation:

```bash
uv run uvicorn app.main:app --reload
curl http://127.0.0.1:8000/health
curl -s -X POST http://127.0.0.1:8000/api/v1/estimate \
  -H "Content-Type: application/json" \
  -d '{"transcription":"The client needs a landing page with HubSpot integration."}'
```

## 16. API collection

The folder `api-collection/Estimador CAG/` holds a versioned collection for manual testing.

Current pieces:

- `opencollection.yml`: collection metadata.
- `environments/local.yml`: sets `baseUrl=http://127.0.0.1:8000`.
- `Health.yml`: health request.
- `Read Root.yml`: root index request.
- `estimations/Create Estimate.yml`: `POST /api/v1/estimate`.
- `estimations/*.yml`: sample request bodies (size/category naming may vary by fixture set).

The collection helps validate contracts without relying only on `curl`.

## 17. Documentation and sync

Canonical source:

```text
second-brain-master-ia/proyectos/estimador-cag/
```

Versioned mirror:

```text
proyectos/estimador-cag/docs/
```

After editing notes in the Second Brain, sync from the repository root:

```bash
bash scripts/sync-estimador-cag-docs.sh
```

The script uses `rsync --delete`, so `docs/` is a true mirror. Files removed in the vault disappear from the git copy.

## 18. Security and secrets

Project rules:

- `.env` is local and must not be committed.
- `.env.example` contains placeholders or non-sensitive defaults only.
- API keys are read from environment variables.
- Logs must not include credentials or full transcriptions.
- Tests must not require real keys.
- Do not document real tokens in Second Brain notes that sync into the repository.

## 19. Evolution guide

As the project grows, keep these boundaries:

- New endpoints: add routers under `app/routers/`.
- Business logic or providers: keep in `app/services/`.
- Reusable prompt context: place under `app/context/`.
- New variables: update `app/config.py`, `.env.example`, `README.md`, and this technical doc.
- API contract changes: update tests, API collection, expected OpenAPI, and docs.
- Prompt or context changes: bump `PROMPT_VERSION` or `EXAMPLES_VERSION`.

Possible next technical steps:

- Add a structured schema for estimates if programmatic consumption is needed.
- Add metadata filters or hybrid search when retrieval quality requires tuning beyond pure vector rank.
- Add retries/backoff once the current fallback baseline is stable.
- Add tracing or request logging if local observability is insufficient.
- Add CI when the project has a stable remote or PR workflow.

## 20. Troubleshooting

### `No provider could be configured from LLM_PROVIDERS...`

The app fails fast at startup when no provider can be built and static fallback is disabled.

Check:

```bash
cd proyectos/estimador-cag
cp .env.example .env
```

Then add at least one real provider key only in `.env`.

### `503 Service Unavailable` with authentication/configuration message

By default, auth/configuration errors do not fallback silently. Check API keys and model names, or set `LLM_AUTH_FALLBACK=true` if you explicitly want auth fallback behavior.

### `422 Unprocessable Entity`

The body is missing `transcription`, or it is empty after `strip()`.

### `503 Service Unavailable`

The service could not produce an estimate. Typical causes: missing credentials, timeout, rate limit, provider error, or empty model response.

### `/favicon.ico` returns `404`

Expected. There is no favicon asset; some browsers request it automatically.

### Changes under `second-brain-master-ia` do not appear in `docs/`

Run from the repository root:

```bash
bash scripts/sync-estimador-cag-docs.sh
```

### `DATABASE_URL is required to run Alembic migrations`

Export a DSN before `uv run alembic upgrade head`. From the host against Compose Postgres:

```bash
export DATABASE_URL=postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator
```

Inside the `app` container, Compose already injects `postgresql+asyncpg://estimator:estimator@postgres:5432/estimator`.

### `the greenlet library is required...` when running Alembic

Ensure dependencies are synced (`uv sync`). `greenlet` is a runtime dependency for async SQLAlchemy migrations.

### Postgres container unhealthy

Wait for `pg_isready` (healthcheck) or inspect logs:

```bash
docker compose logs postgres
docker compose ps postgres
```

## 21. Embedding pipeline (Session 07)

Isolated module under `app/embedding_pipeline/`. It does **not** import `app/services/semantic_cache/`. Postgres persistence and semantic search are separate increments — see [§22](#22-postgres-pgvector-baseline-feature-036) and [§23](#23-semantic-search-endpoint-feature-038).

### HTTP routes

| Method | Path | Handler |
|--------|------|---------|
| `POST` | `/api/v1/embeddings/ingest` | `app/routers/embeddings.py` → `run_persistent_ingest()` |
| `POST` | `/api/v1/search` | `app/routers/search.py` → `run_semantic_search()` |

**Ingest:** one `Budget` per request (`PersistentIngestRequest`). Response: `PersistentIngestResponse` metadata (no raw vectors). Duplicate `source_path` → `409`.

**Search:** natural-language `query` + optional `k` (default 5, max 50). Response: ranked `SearchResult[]` with cosine `distance`. Empty corpus → `200` with `results: []`.

### Module layout

| Path | Role |
|------|------|
| `schemas.py` | `Budget`, `Chunk`, ingest + search contracts (`SearchRequest`, `SearchResponse`, …) |
| `adapters.py` | `BudgetToDocumentAdapter`, `make_component_id` |
| `chunker.py` | `JSONStructuralChunker` — markdown template, tiktoken from settings |
| `embedder.py` | `OpenAIEmbedder` — single lazy `AsyncOpenAI` client |
| `ingest.py` | `run_ingest()` — in-memory CLI path |
| `persistent_ingest.py` | `run_persistent_ingest()` — transactional Postgres ingest |
| `repository.py` | `EmbeddingIngestRepository` — document/chunk writes |
| `search.py` | `run_semantic_search()` — embed query + repository lookup |
| `search_repository.py` | `SemanticSearchRepository` — pgvector `cosine_distance` SQL |
| `loaders/filesystem.py` | Non-recursive `*.json` iteration |
| `parsers/budget_json.py` | `parse_budget_file`, `BudgetParseError` |
| `parsers/registry.py` | `get_parser("json")` |

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `EMBEDDING_PIPELINE_MODEL` | `text-embedding-3-small` | Embedding model (embedder + chunker tiktoken) |
| `EMBEDDING_PIPELINE_BATCH_SIZE` | `100` | Batch size for `embed_many` |
| `OPENAI_API_KEY` | — | Required for embed paths (not for offline tests) |
| `OPENAI_TIMEOUT_SECONDS` | `30` | Embedder HTTP timeout |

### Scripts (`app/scripts/`)

| Module | Purpose |
|--------|---------|
| `compare.py` | Cosine similarity between two texts |
| `ingest_from_dir.py` | Load `*.json` budgets from a directory; `--dry-run` chunks only |
| `preflight_embedding_pipeline.py` | Settings, tiktoken, optional `--live` ping |
| `inspect_fixtures.py` | Valid/invalid budget JSON counts via loader + parser |
| `architecture_decision.py` | Offline CAG / Hybrid / RAG heuristic |

### Verification

```bash
uv run pytest tests/embedding_pipeline/
uv run pytest tests/embedding_pipeline/test_milestone_e2e.py
```

Heavy (real key): `uv run pytest -m slow tests/embedding_pipeline/ --run-heavy`

See also [docs/work-items/adr-001-embedding-pipeline-vs-estimator-ingestion.md](../work-items/adr-001-embedding-pipeline-vs-estimator-ingestion.md).

## 22. Postgres pgvector baseline (feature-036)

Increment 1 of the semantic-search milestone. Establishes a reproducible database layer; feature-037 wires ingest to these tables; feature-038 reads embeddings for search.

### Docker service

| Setting | Value |
|---------|-------|
| Image | `pgvector/pgvector:pg16` |
| Database / user / password | `estimator` (local placeholders only) |
| Host port | `5432` |
| Healthcheck | `pg_isready -U estimator -d estimator` |

The `app` service depends on healthy `postgres` and receives `DATABASE_URL=postgresql+asyncpg://estimator:estimator@postgres:5432/estimator`.

### Application layout

| Path | Role |
|------|------|
| `app/database.py` | `Base`, async engine factory, `async_sessionmaker`, `session_scope` helper |
| `app/models/document.py` | `documents` table — unique `source_path`, JSONB `metadata` |
| `app/models/chunk.py` | `chunks` table — FK `ON DELETE CASCADE`, `Vector(1536)`, GIN on `metadata` |
| `alembic/env.py` | Async migrations; reads `DATABASE_URL` from `Settings`; registers pgvector types |
| `alembic/versions/0001_initial_schema.py` | `CREATE EXTENSION vector`, tables, non-vector indexes |
| `alembic/versions/0002_add_chunks_embedding_hnsw_index.py` | HNSW cosine index on `chunks.embedding` (feature-040) |

### Schema summary

**`documents`:** `id`, `source_path` (unique), `document_type`, `ingested_at`, `metadata` (JSONB).

**`chunks`:** `id`, `document_id` → `documents.id`, `chunk_type`, `content`, `embedding` (`vector(1536)`, nullable), `metadata` (JSONB), `created_at`.

Indexes: `ix_documents_source_path`, `ix_chunks_document_id`, `ix_chunks_chunk_type`, `ix_chunks_metadata_gin`, `ix_chunks_embedding_hnsw` (HNSW, `vector_cosine_ops`, partial on non-null embeddings). See [§24](#24-hnsw-vector-index-feature-040).

### Manual verification checklist

1. Start Postgres: `docker compose up -d postgres`
2. Connection: `docker compose exec postgres psql -U estimator -d estimator -c "SELECT version();"`
3. Migrate: `export DATABASE_URL=postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator && uv run alembic upgrade head`
4. Inspect: `docker compose exec postgres psql -U estimator -d estimator -c "\dt"` and `\d chunks`
5. Confirm extension: `SELECT extname FROM pg_extension WHERE extname = 'vector';`
6. Confirm HNSW index: `SELECT indexname FROM pg_indexes WHERE indexname = 'ix_chunks_embedding_hnsw';`
7. Run observability report: `docker compose exec -T postgres psql -U estimator -d estimator < scripts/pgvector_observability.sql`
8. Regression: `uv run pytest tests/embedding_pipeline/` (no live DB required by default)

### Automated tests (no live Postgres)

```bash
uv run pytest tests/test_config.py -k database_url
uv run pytest tests/test_database_models.py tests/test_alembic_migration.py
```

### Visual clients (host → Compose Postgres)

Connect with any desktop SQL client using:

| Field | Value |
|-------|-------|
| Host | `127.0.0.1` |
| Port | `5432` |
| Database | `estimator` |
| User | `estimator` |
| Password | `estimator` |

Recommended GUI clients:

- **[DBeaver](https://dbeaver.io/)** — free, cross-platform; good default for schema browsing and ad-hoc SQL.
- **[TablePlus](https://tableplus.com/)** or **[Postico](https://eggerapps.at/postico2/)** — native macOS UIs, fast for local dev.
- **[pgAdmin](https://www.pgadmin.org/)** — full-featured web/desktop admin (heavier than TablePlus).

The ingest endpoint writes to these tables after feature-037; search reads `chunks.embedding` after feature-038.

## 23. Semantic search endpoint (feature-038)

Increment 3 of the semantic-search milestone. Exposes persisted chunks through `POST /api/v1/search` using the same embedding model as ingest.

### Request / response

| Field | Type | Notes |
|-------|------|-------|
| Request `query` | `str` | Non-empty after trim |
| Request `k` | `int` | Default `5`, min `1`, max `50` |
| Response `search_time_ms` | `int` | Wall-clock (includes `embed_one`) |
| Result `distance` | `float` | pgvector cosine distance via `<=>`; lower = closer |

Status codes: `200` (empty corpus → `results: []`), `422`, `503` (no `DATABASE_URL`), `500` (safe generic detail).

### Application layout

| Path | Role |
|------|------|
| `app/routers/search.py` | HTTP route, DI, error mapping |
| `app/embedding_pipeline/search.py` | `run_semantic_search()` orchestration |
| `app/embedding_pipeline/search_repository.py` | SQLAlchemy select with `cosine_distance`, null filter, order, limit |

### SQL behaviour

```text
SELECT …, chunks.embedding <=> :query_vector AS distance
FROM chunks
WHERE chunks.embedding IS NOT NULL
ORDER BY distance ASC
LIMIT :k
```

No application SQL change is required — the planner may use `ix_chunks_embedding_hnsw` when the operator class matches `cosine_distance` (`<=>`). On very small corpora the planner can still choose a sequential scan until statistics favour ANN; see [§24](#24-hnsw-vector-index-feature-040).

### Distance interpretation (operational)

- Strong match on this corpus often shows distances ~0.2–0.4 when query vocabulary aligns with chunk text (e.g. OAuth + fintech query vs OAuth fintech chunk).
- Moderate similarity often appears ~0.65–0.71 when signals conflict (e.g. SAML + education query vs OAuth finance chunks).
- Semantic search is not keyword search: absent terms (SAML) do not block related concepts (OAuth, API, authentication) from ranking highly.
- Duplicate ingests of the same `source_path` can produce identical chunks at different IDs occupying multiple top-k slots.

Worked example with request/response analysis: [feature-038 work item](../work-items/feature-038-semantic-search-endpoint-pgvector.md#manual-query-analysis-verified-on-compose-postgres).

### Verification

```bash
uv run pytest tests/embedding_pipeline/test_search_*.py -q
uv run pytest tests/embedding_pipeline/ -q

# Manual (Compose, corpus ingested, OPENAI_API_KEY set)
curl -sS -X POST http://127.0.0.1:8000/api/v1/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"REST API with SAML authentication for public educational sector","k":5}'
```

Automated tests mock `OpenAIEmbedder` and DB session; they do not require live Postgres or OpenAI.

### Retrieval debug API (features 042-044)

Feature-042 adds the internal observability layer without changing `POST /api/v1/search`. Feature-043 adds the lexical full-text branch so operators can compare semantic retrieval with exact-term matching for acronyms, versions, standards, and identifiers. Feature-044 adds hybrid fusion, ranking diff, and controlled explanations over vector + lexical evidence.

| Path | Role |
|------|------|
| `app/routers/retrieval_debug.py` | HTTP routes, DI, safe errors, completion logging |
| `app/embedding_pipeline/retrieval_debug.py` | Vector, lexical, and hybrid branch orchestration, score normalization, explanations, diff assembly, chunk inspection service |
| `app/embedding_pipeline/fusion.py` | Pure Reciprocal Rank Fusion, weighted fusion, ranking diff, and explanation helpers |
| `app/embedding_pipeline/lexical_search_repository.py` | Postgres full-text search statement and lexical row mapping |
| `app/embedding_pipeline/retrieval_debug_repository.py` | Chunk/document/neighbor reads and optional single-chunk distance query |
| `app/embedding_pipeline/retrieval_debug_schemas.py` | Request/response schemas and nullable branch container |

`POST /api/v1/retrieval-debug` request:

```json
{
  "query": "JWT refresh token rotation for OAuth2 REST API",
  "strategies": ["vector", "lexical", "hybrid"],
  "vector": {"top_k": 20, "threshold": 0.6},
  "lexical": {"top_k": 20},
  "hybrid": {"enabled": true, "method": "rrf", "rrf_k": 60},
  "max_results": 10
}
```

Response shape:

- `branches.vector[]`: vector rank, ids, `distance`, normalized `score`.
- `branches.lexical[]`: lexical rank, ids, normalized `score`, and `matched_terms`; `distance` is `null` because lexical rank is not a vector distance.
- `branches.hybrid[]`: fused rank, ids, and `score`; default method is Reciprocal Rank Fusion (`score = Σ weight/(rrf_k + rank)`), while `method="weighted"` combines normalized branch scores with server-normalized weights.
- `branches.rerank`: `null`; requested rerank still produces a warning until feature-045.
- `final_results[]`: hybrid requests are ordered by `fusion_rank` and include `fusion_score`, semantic fields, lexical fields, `source_strategies`, metadata, excerpt, and controlled explanations.
- `diff`: `common`, `vector_only`, `lexical_only`, `hybrid_rescued`, `big_movers`, `dropped_by_threshold`, and `dropped_by_rerank` (empty until feature-045).
- `timings_ms`: `vector`, `lexical`, `hybrid`, and `total`.

Controlled explanation signals:

- `semantic_strong`, `semantic_weak`, `below_threshold`
- `lexical_exact_match`
- `branch_consensus`
- `hybrid_rescued`

Lexical SQL baseline:

```sql
SELECT id, document_id, chunk_type, content, metadata,
       ts_rank_cd(to_tsvector('english', content), websearch_to_tsquery('english', :query)) AS ts_rank,
       ts_headline('english', content, websearch_to_tsquery('english', :query), 'StartSel=<<, StopSel=>>') AS headline
FROM chunks
WHERE to_tsvector('english', content) @@ websearch_to_tsquery('english', :query)
ORDER BY ts_rank DESC
LIMIT :top_k;
```

Lexical `score` is min-max normalized over the branch's `ts_rank_cd` values. When every lexical rank is equal, all returned lexical entries receive `score = 1.0`. `matched_terms` is extracted from highlighted `ts_headline` output, lower-cased, deduplicated, and sorted for deterministic debug output. This is intentionally an on-the-fly sequential-scan baseline; indexed `tsvector` or `pg_trgm` work belongs to `feature-048`.

Chunk inspector:

```bash
curl -sS "http://127.0.0.1:8000/api/v1/retrieval-debug/chunks/156?query=OAuth%20backend"
```

Status/error contract: empty corpus returns `200` with empty lists, invalid input returns `422`, unknown chunk returns `404`, empty `DATABASE_URL` returns `503`, unexpected failures return safe `500` details.

## 24. HNSW vector index (feature-040)

Increment after the semantic-search milestone. Adds an approximate nearest-neighbour (ANN) index on `chunks.embedding` aligned with the existing `cosine_distance` search path.

### Index definition

Migration `0002_add_chunks_embedding_hnsw_index.py`:

```sql
CREATE INDEX ix_chunks_embedding_hnsw
ON chunks
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64)
WHERE embedding IS NOT NULL;
```

| Parameter | Value | Notes |
|-----------|-------|-------|
| Method | `hnsw` | pgvector ANN index |
| Operator class | `vector_cosine_ops` | Must match `<=>` / `cosine_distance` |
| `m` | 16 | pgvector default — graph connectivity |
| `ef_construction` | 64 | pgvector default — build-time candidate list |
| Predicate | `embedding IS NOT NULL` | Mirrors `SemanticSearchRepository` filter |

Search-time recall tuning uses the session parameter `hnsw.ef_search` (default `40`). Increase for higher recall at the cost of latency.

### Query planner behaviour

The search SQL from feature-038 is unchanged. After `alembic upgrade head`, verify the index exists:

```bash
docker compose exec -T postgres psql -U estimator -d estimator -c \
  "SELECT indexname, indexdef FROM pg_indexes WHERE indexname = 'ix_chunks_embedding_hnsw';"
```

Diagnostic `EXPLAIN` (small corpora may still prefer sequential scan without this hint):

```sql
ANALYZE chunks;
SET enable_seqscan = off;
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, embedding <=> (SELECT embedding FROM chunks WHERE embedding IS NOT NULL LIMIT 1) AS distance
FROM chunks
WHERE embedding IS NOT NULL
ORDER BY distance
LIMIT 5;
```

Expect `Index Scan using ix_chunks_embedding_hnsw` when the planner chooses ANN. Do **not** set `enable_seqscan = off` in production — use only for local diagnostics.

### Observability script

`scripts/pgvector_observability.sql` returns stable dashboard columns:

- `nombre_tabla`, `nombre_columna_vector`, `dimensiones`
- `total_chunks`, `total_vectores`
- `nombre_indice`, `metodo_indice`, `operator_class`
- `tamano_indice_bytes`, `tamano_indice_pretty`, `tamano_tabla_pretty`
- `idx_scan`, `last_idx_scan`
- memory settings (`shared_buffers`, `effective_cache_size`, `work_mem`)

```bash
docker compose exec -T postgres psql -U estimator -d estimator < scripts/pgvector_observability.sql
```

**Alerts to watch:**

- `nombre_indice` is null → no HNSW/IVFFlat index on vector columns.
- `idx_scan = 0` after sustained search traffic → index may not be used (check `EXPLAIN`, operator class, corpus size).
- Index size growing faster than row count → review `m`, `ef_construction`, or consider `halfvec` in a future feature.

### Verified snapshot (Compose, 2026-06-14)

| Metric | Before index | After index |
|--------|--------------|-------------|
| Chunks / vectors | 39 / 39 | 39 / 39 |
| HNSW indexes | 0 | 1 (`ix_chunks_embedding_hnsw`) |
| Index size | — | ~312 kB |
| Table total | ~504 kB | ~816 kB |

Work item: [feature-040](../work-items/feature-040-chunks-hnsw-vector-index.md).

### Verification

```bash
uv run pytest tests/test_alembic_migration.py -q
export DATABASE_URL=postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator
uv run alembic upgrade head
docker compose exec -T postgres psql -U estimator -d estimator < scripts/pgvector_observability.sql
```

Downgrade path: `uv run alembic downgrade 0001` drops `ix_chunks_embedding_hnsw` only.

## 24. Worktree task orchestrator

`scripts/worktree_tasks.py` prepares isolated Git worktrees for feature work items. It does not replace `/start-task`; it prepares a clean directory, canonical branch, local instructions, and status metadata so an agent or developer can run `/start-task` inside that worktree.

Example manifest:

```bash
uv run python scripts/worktree_tasks.py plan -f docs/technical/worktree-task-orchestrator.example.yaml
```

Prepare a selected task:

```bash
uv run python scripts/worktree_tasks.py prepare -f docs/technical/worktree-task-orchestrator.example.yaml --only 042 --dry-run
uv run python scripts/worktree_tasks.py prepare -f docs/technical/worktree-task-orchestrator.example.yaml --only 042
```

Inspect and clean up:

```bash
uv run python scripts/worktree_tasks.py status -f docs/technical/worktree-task-orchestrator.example.yaml
uv run python scripts/worktree_tasks.py cleanup -f docs/technical/worktree-task-orchestrator.example.yaml --only 042 --dry-run
```

Preview the future Cursor SDK runner without launching agents:

```bash
uv run python scripts/worktree_tasks.py run -f docs/technical/worktree-task-orchestrator.example.yaml --only 042 --dry-run
```

Safety notes:

- Worktrees live outside the repository tree by default (`../master-ia-worktrees`) to avoid nested repo indexing and test discovery surprises.
- `.env` is symlinked by default when present; secret values are never printed or written to status files.
- Each worktree should run its own `uv sync --group dev` before full local work.
- The default fast test suite is safe to run in parallel. Live Postgres/Redis checks should be serialized because the Compose stack uses fixed shared ports.
- Cursor SDK execution is a future extension point. The `run --dry-run` command shows the prompts that would be sent, but it does not launch agents yet. Local SDK runs still consume Cursor usage through `CURSOR_API_KEY`; without on-demand enabled, they can stop when included usage is exhausted.

The checked-in sample uses currently versioned work items 042 and 043. Extend it with 044-048 once those work-item documents are committed to Git.

