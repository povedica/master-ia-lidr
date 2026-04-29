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

## 1. Overview

`estimador-cag` is a FastAPI service that accepts a client meeting transcription and returns a structured software estimate.

The project uses **Context-Augmented Generation (CAG)** in a deliberately small form:

- Static context lives in `app/context/examples.py`.
- The app builds a `system prompt` with instructions and prior examples.
- The live transcription is sent as the `user` message.
- A deterministic assessment classifies the request into one mode (`basic`, `standard`, `professional`, `expert_review`).
- A provider chain (`openai,anthropic` by default) returns an estimate with assumptions, a task/hours table, and delivery notes.

The first version does not include persistence, authentication, a frontend, or production deployment. It is an AI Engineering baseline meant for learning and safe iteration.

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
| Manual API client | OpenCollection/Bruno collection under `api-collection/` | Versioned manual checks alongside the code. |

## 3. Libraries and frameworks

Runtime dependencies declared in `pyproject.toml`:

- `fastapi[standard]`: web framework, validation, OpenAPI docs.
- `uvicorn[standard]`: local ASGI server.
- `pydantic-settings`: typed configuration from the environment.
- `openai`: official SDK for OpenAI.
- `anthropic`: official SDK for Anthropic.
- `python-dotenv`: load `.env` in local development.

Development dependencies:

- `pytest`: test runner.
- `pytest-asyncio`: async test support.
- `httpx`: HTTP client used by FastAPI `TestClient` and tests.

Important rule: tests mock provider SDK clients. The default suite must not depend on real provider API keys.

## 4. Local setup

Requirements:

- Python 3.11.
- `uv` on the host.
- At least one provider key (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY`) if you want live model estimates.

From the repository root:

```bash
cd proyectos/estimador-cag
uv sync --group dev
cp .env.example .env
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
| `APP_ENV` | No | `local` | Logical runtime environment. Logged at startup. |
| `DEV_MODE` | No | `false` | When `true`, responses include `usage` and estimated cost. |
| `LOG_LEVEL` | No | `INFO` | Base logging level. |

Loading is centralized in `app/config.py` via `Settings`, with `.env` as a local source and `extra="ignore"` so unknown variables do not break startup.

## 6. Scripts and commands

Main subproject commands:

```bash
cd proyectos/estimador-cag
uv sync --group dev
uv run uvicorn app.main:app --reload
uv run pytest
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
│   │   ├── prompt_loader.py
│   │   └── prompts/
│   │       ├── basic.txt
│   │       ├── standard.txt
│   │       ├── professional.txt
│   │       └── expert_review.txt
│   ├── routers/
│   │   ├── __init__.py
│   │   └── estimations.py
│   └── services/
│       ├── __init__.py
│       ├── domain_guardrails.py
│       ├── estimation_engine.py
│       └── llm_service.py
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
│   ├── test_estimation_engine.py
│   ├── test_prompt_loader.py
│   └── test_llm_service.py
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
| `app/context/prompts/` | Mode-specific prompt fragments (`*.txt`) loaded at runtime by `prompt_loader.py`. |
| `app/services/providers/` | Provider implementations (`openai`, `anthropic`, `static_fallback`) and chain registry. |
| `app/context/examples.py` | Static few-shot examples. |
| `tests/` | Unit and API tests with a mocked provider. |
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
    Service->>Service: input_assessment(detail, ambiguity, complexity, risk)
    Service->>Service: mode_eligibility_guardrail(allowed/blocked modes)
    Service->>Service: route_mode_from_context_quality
    Service->>Context: load_examples()
    Context-->>Service: list[EstimationExample]
    Service->>Service: build_system_prompt(examples, mode)
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
    Router->>Router: request_id, timestamp, latency_ms, versions
    Router-->>Client: EstimateResponse
```

Mode assessment reference contract:

```json
{
  "detail_level": "low | medium | high | expert",
  "recommended_mode": "basic | standard | professional | expert_review",
  "reason": "The input includes authentication and mobile features, but lacks roles, backend constraints, integrations and non-functional requirements."
}
```

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

Business guardrail response when context quality is insufficient:

```json
{
  "allowed_modes": ["basic", "standard"],
  "blocked_modes": ["professional", "expert_review"],
  "reason": "Input detail is insufficient."
}
```

Precision guidance:
"More detailed input enables better scope control, clearer assumptions, lower uncertainty and a more defensible estimation range."

Traceability fields:

- `request_id`: per-request identifier.
- `timestamp`: UTC response time.
- `latency_ms`: total duration measured in the router.
- `prompt_version`: prompt template version.
- `examples_version`: static context version.

## 10. CAG design

In this project, CAG means the model receives **team-maintained static context**, not data retrieved from a vector database.

Message pattern:

```text
[system]    Instructions + reference estimation examples
[user]      Meeting transcription
[assistant] Generated estimate
```

`build_system_prompt()` includes:

- Role: expert software estimator.
- Mode-specific instructions loaded from `app/context/prompts/<mode>.txt` (editable without changing Python code).
- Instruction to mirror structure, detail level, and pragmatism of the examples.
- Expected format: assumptions, task/hours table, delivery notes.
- Examples from `EXAMPLES`.

Versioning:

- `PROMPT_VERSION = "v2"` in `app/services/llm_service.py`.
- `EXAMPLES_VERSION = "static-v1"` in `app/services/llm_service.py`.
- Bump `PROMPT_VERSION` when prompt composition changes or default prompt-file wording materially changes estimation behavior.
- Bump `EXAMPLES_VERSION` when example content changes behavior in a meaningful way.

## 11. API contract

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

Response with `DEV_MODE=false`:

```json
{
  "estimation": "## Estimation: ...",
  "mode": "standard",
  "model": "gpt-4o-mini",
  "provider": "openai",
  "request_id": "est_abc123def456",
  "timestamp": "2026-04-27T10:00:00Z",
  "latency_ms": 1800,
  "prompt_version": "v2",
  "examples_version": "static-v1"
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

Degraded response (when static fallback is used):

```json
{
  "estimation": "## Estimation: Temporary degraded mode ...",
  "model": "static-v1",
  "provider": "static_fallback",
  "request_id": "est_abc123def456",
  "timestamp": "2026-04-27T10:00:00Z",
  "latency_ms": 1800,
  "prompt_version": "v2",
  "examples_version": "static-v1",
  "degraded": true
}
```

Response with `DEV_MODE=true`:

```json
{
  "estimation": "## Estimation: ...",
  "mode": "standard",
  "model": "gpt-4o-mini",
  "provider": "openai",
  "request_id": "est_abc123def456",
  "timestamp": "2026-04-27T10:00:00Z",
  "latency_ms": 1800,
  "prompt_version": "v2",
  "examples_version": "static-v1",
  "usage": {
    "prompt_tokens": 920,
    "completion_tokens": 410,
    "total_tokens": 1330,
    "estimated_cost_usd": 0.000384
  }
}
```

## 12. Response metadata

Operational metadata (always present):

- `request_id`: correlates a response with logs or incident reports.
- `timestamp`: UTC time when the response was produced.
- `latency_ms`: end-to-end request duration from the router.
- `prompt_version`: prompt instruction version.
- `examples_version`: few-shot context version.
- `provider`: provider that produced the response (`openai`, `anthropic`, `static_fallback`).
- `model`: model identifier reported by the provider implementation.
- `mode`: adaptive estimation mode selected by service-level deterministic routing.
- `degraded`: only present when static fallback is used.

Development metadata (only when `DEV_MODE=true`):

- `usage.prompt_tokens`: input tokens reported by the provider.
- `usage.completion_tokens`: output tokens reported by the provider.
- `usage.total_tokens`: total reported by the provider.
- `usage.estimated_cost_usd`: local approximation from known model pricing.

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

The router maps:

- `DomainGuardrailError` to `422 Unprocessable Entity`
- `EstimationError` to `503 Service Unavailable`

This avoids leaking stack traces or internal details to API clients.

## 15. Testing and validation

Main command:

```bash
cd proyectos/estimador-cag
uv run pytest
```

Current coverage:

- `tests/test_config.py`: settings and environment overrides.
- `tests/test_llm_service.py`: prompt construction, transcription validation, timeout, empty content, mocked success path.
- `tests/test_api.py`: root, health, response shape, `DEV_MODE`, validation, `503` mapping.

Testing rules:

- Do not use real API keys in tests.
- Mock provider SDK clients.
- Test project-owned logic: prompts, minimal parsing, metadata, errors, settings.
- Keep tests fast and deterministic.

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
- Persist estimates and metadata if auditability is required.
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
