# Estimador CAG

**Context-Augmented Generation (CAG) API for software project estimation.**

A FastAPI service that turns structured project context — meeting transcripts, briefs, and attachments — into software estimates. Few-shot reference examples are sampled from a unified flat pool under `app/context/examples/` and injected into the system prompt; the composed project brief is sent as the user message to the configured LLM provider.

Built as an **AI Engineering learning baseline**: typed settings, provider abstraction, guardrails, optional semantic cache, session memory, and a React web UI — without production auth or persistent storage by default.

---

## Features

| Area | What you get |
|------|----------------|
| **CAG** | Few-shot examples from a flat `app/context/examples/*.txt` pool (2–4 samples per request); depth and layout come from guided-form fields (`detail_level`, `output_format`). |
| **API surfaces** | Text (v1), structured JSON (v2), SSE streaming (v1), and session-based simplified submit. |
| **Guardrails** | Domain filter, prompt-injection heuristics, PII checks, and output semantic validation on the v2 pipeline. |
| **Sessions** | In-memory multi-turn sessions with sliding-window history, derived metadata merge, and attachment ingestion. |
| **Providers** | OpenAI and Anthropic via [LiteLLM](https://github.com/BerriAI/litellm), with ordered fallback and optional static degraded mode. |
| **Semantic cache** | Optional Redis Stack / RediSearch vector cache for `POST /api/v2/estimate` (off by default). |
| **Observability** | Optional [Langfuse](https://langfuse.com) traces via OpenTelemetry (off by default). |
| **Web UI** | React + Vite + TypeScript workbench in `web/` with session sidebar, multipart uploads, and theme controls. |

---

## Table of contents

1. [Requirements](#requirements)
2. [Quick start](#quick-start)
3. [Running the application](#running-the-application)
4. [Architecture](#architecture)
5. [Web UI](#web-ui)
6. [API reference](#api-reference)
7. [Capabilities](#capabilities)
8. [Configuration](#configuration)
9. [Project structure](#project-structure)
10. [Tests](#tests)
11. [Semantic search with pgvector](#semantic-search-with-pgvector)
12. [Documentation](#documentation)
13. [Troubleshooting](#troubleshooting)
14. [Security](#security)

---

## Requirements

| Path | Requirements |
|------|-------------|
| **Docker (full stack)** | [Docker](https://docs.docker.com/get-docker/) with Compose v2 — no Python or Node needed on the host |
| **Local development** | Python **3.11.x** ([uv](https://docs.astral.sh/uv/)), Node.js **20+** with npm (for `web/`) |

> Python is pinned to `>=3.11,<3.12` in `pyproject.toml`.

---

## Quick start

1. Copy the environment template and add at least one provider key:

```bash
cp .env.example .env
# Set OPENAI_API_KEY and/or ANTHROPIC_API_KEY — never commit .env
```

2. Start the full stack with Docker:

```bash
docker compose up --build
```

3. Verify the API:

```bash
curl -s http://127.0.0.1:8000/health
```

| Service | URL |
|---------|-----|
| FastAPI API | `http://127.0.0.1:8000` |
| OpenAPI docs | `http://127.0.0.1:8000/docs` |
| Web UI (nginx) | `http://127.0.0.1:5175` |
| Redis Stack | `redis://127.0.0.1:6379` |
| Redis Insight | `http://127.0.0.1:5540` — add database: host `redis`, port `6379` |
| Postgres (pgvector) | `postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator` |

For local development without Docker, see [Running the application](#running-the-application).

---

## Running the application

### Docker (recommended)

Runs the API, web UI, Redis Stack, Redis Insight, and Postgres (pgvector) in containers.

**Production mode:**

```bash
docker compose up --build
```

If you only start `app`, Redis and Postgres may not run. Either use `docker compose up` as above or start dependencies explicitly: `docker compose up -d redis postgres`. With the default compose file, `app` depends on `redis` and healthy `postgres`, so a normal `up` brings the full stack up.

Set `SEMANTIC_CACHE_REDIS_URL` in `.env` when exercising the semantic cache: use `redis://redis:6379/0` for the `app` container, or `redis://127.0.0.1:6379/0` if the API runs on the host while Redis runs in Compose.

**Development mode** (API live-reload via Uvicorn `--reload`, bind-mounted source):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

The dev override bind-mounts the repo into the container and restarts the API on code changes. The `web` service remains the same static nginx container.

**Custom API URL for the web image:**

```bash
docker compose build --build-arg VITE_API_BASE_URL=http://192.168.1.10:8000 web
docker compose up
```

### Local development

**Terminal 1 — API:**

```bash
uv sync --group dev
uv run uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`.

**Terminal 2 — Web UI (optional, for Vite HMR):**

```bash
cd web
cp .env.example .env.local
# Optionally edit VITE_API_BASE_URL (default: http://127.0.0.1:8000)
npm install
npm run dev
```

Open the URL Vite prints (default `http://127.0.0.1:5173`). Ensure that origin is listed in `FRONTEND_ORIGINS` in your `.env` (defaults already include standard Vite dev URLs).

**Optional — Redis for semantic cache (host API):**

```bash
docker compose up -d redis
# In .env: SEMANTIC_CACHE_REDIS_URL=redis://127.0.0.1:6379/0
```

---

## Architecture

Layered FastAPI application: routers orchestrate HTTP; services own business logic; guardrails and provider access stay behind service boundaries.

```mermaid
flowchart LR
    subgraph clients [Clients]
        Web[Web UI]
        Curl[curl / API collection]
    end

    subgraph api [FastAPI]
        R1[v1 estimations]
        R2[v2 structured]
        RS[sessions]
        EMB[embeddings ingest]
        SR[search]
    end

    subgraph core [Core services]
        ES[EstimationService]
        SS[SimplifiedSessionService]
        GP[Guardrail pipeline]
        SC[Semantic cache]
        EP[Embedding pipeline]
    end

    subgraph external [External]
        LLM[LiteLLM → OpenAI / Anthropic]
        EMBAPI[OpenAI embeddings]
        Redis[(Redis Stack)]
        PG[(Postgres pgvector)]
        LF[Langfuse OTEL]
    end

    Web --> RS
    Curl --> R1 & R2 & RS & EMB & SR
    R1 --> ES
    R2 --> GP --> ES
    RS --> SS --> ES
    GP --> SC
    SC --> Redis
    ES --> LLM
    ES -.-> LF
    EMB --> EP
    SR --> EP
    EP --> EMBAPI
    EP --> PG
```

| Layer | Location | Responsibility |
|-------|----------|----------------|
| HTTP | `app/routers/` | Validation, status codes, response assembly |
| Middleware | `app/middleware/`, `app/cors.py` | Cross-cutting HTTP concerns (LLM-call audit, CORS) |
| Business | `app/services/` | CAG prompts, provider chain, sessions, attachments, semantic cache, observability |
| Guardrails | `app/guardrails/` | Input/output policies, audit, rollout modes (incl. ACB policy) |
| Schemas | `app/schemas/` | Pydantic request/response models |
| Context | `app/context/` | Few-shot example pools and legacy mode prompts |
| Prompts | `app/prompts/` | Jinja2 templates: `estimation/` (v1 retro, v2 default), `acb/` (Actor-Critic-Boss) |
| Embedding pipeline | `app/embedding_pipeline/` | Budget chunking, OpenAI embeddings, ingest, and semantic search (isolated from semantic cache) |
| Persistence | `app/database.py`, `app/models/` | Async SQLAlchemy engine/session and ORM models (Postgres + pgvector) |

For sequence diagrams, error mapping, and logging details, see [docs/technical/README.md](docs/technical/README.md).

---

## Web UI

The `web/` package is a **React + Vite + TypeScript** browser UI. On load it creates a session (`POST /api/v1/sessions`), lists recent sessions in a sidebar (`GET /api/v1/sessions`), and submits the simplified form to `POST /api/v1/sessions/{session_id}/estimate`. **Project metadata** and the structured **estimate** render in separate panels.

| Mode | How it runs |
|------|-------------|
| **Docker** | Static nginx container — assets built at image build time |
| **Local dev** | Vite dev server with HMR on port `5173` |

```bash
cd web
npm run dev      # development
npm run build    # production bundle
npm run preview  # serve dist/ locally
npm run test     # Vitest unit tests
npm run lint     # ESLint
```

See [web/README.md](web/README.md) for environment variables and appearance settings.

---

## API reference

Interactive schema: `http://127.0.0.1:8000/docs`.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe |
| `GET` | `/` | Service index with route links |
| `POST` | `/api/v1/estimate` | Synchronous text estimation |
| `POST` | `/api/v1/estimate/stream` | Markdown estimation with SSE (`chunk` / `done` / `error`) |
| `POST` | `/api/v2/estimate` | Structured synchronous estimation (guardrails + semantic cache) |
| `POST` | `/api/v1/sessions` | Create in-memory session (`201` + `session_id`) |
| `GET` | `/api/v1/sessions` | List sessions for UI sidebar (last 30 days) |
| `GET` | `/api/v1/sessions/{session_id}` | Session detail for restore (payload, metadata, last estimate) |
| `POST` | `/api/v1/sessions/{session_id}/estimate` | Simplified transcript-centered submit |
| `POST` | `/api/v1/embeddings/ingest` | Persist a budget document and its chunk embeddings (Postgres + pgvector) |
| `POST` | `/api/v1/search` | Semantic search over persisted chunks (pgvector cosine distance) |

The `embeddings/ingest` and `search` endpoints belong to the isolated [embedding pipeline](#semantic-search-with-pgvector) and require `DATABASE_URL`.

### Stateless estimation (v1)

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/estimate \
  -H "Content-Type: application/json" \
  -d '{
    "project_summary": "B2B portal for partners to submit requests and track SLA status.",
    "project_type": "web_saas",
    "target_audience": "b2b_smb",
    "project_description": "Responsive web app for authenticated partners to submit structured tickets, follow approval workflows, and view status dashboards.",
    "detail_level": "medium",
    "output_format": "phases_table"
  }'
```

See `app/schemas/estimation_request.py` for the full request shape.

#### Notable request fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `evaluate` | `bool` | `true` | Include structural score and output validation |
| `preprocessing` | `none` \| `inline_cleaning` \| `two_phase` | `none` | Pre-processing strategy before the main estimate |

#### Response fields

| Field | When present | Description |
|-------|-------------|-------------|
| `estimation` | Always | The estimate text |
| `score` | When `evaluate=true` | Structural quality score in `[0, 1]` |
| `structure_evaluation` | When `evaluate=true` | Section-level structural checks |
| `output_validation` | When `evaluate=true` | Mode-specific section checks |
| `degraded` | When static fallback used | `true` if the response is not from a live model |
| `mode`, `model`, `provider`, `request_id`, `timestamp`, `latency_ms`, `prompt_version`, `examples_version`, `usage` | `DEV_MODE=true` only | Operational and debugging metadata |

### Simplified session estimation

Create a session, then submit a transcript-centered estimate. The API returns `project_metadata`, `warnings`, `input_payload`, and a structured `estimate` (same core shape as `POST /api/v2/estimate`).

**Transports**

| Content-Type | Use case |
|--------------|----------|
| `application/json` | SPA / API clients; optional inline `AttachmentRef.content_base64` |
| `multipart/form-data` | Direct file upload; repeat form field `attachments` per file |

Transcript minimum length is **80** characters after trim. On follow-up submits, `project_name`, `project_type`, and `target_audience` may be omitted when the session already has derived metadata.

**Attachment strategy (Path B)**

Files are read in-process and converted to text locally (`DocumentTextExtractor` for `text/plain`, `text/markdown`, `application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`). Path B avoids external file stores or provider Files API keys for the exercise and keeps integration tests deterministic. Path A (provider-native `file_id`) is deferred.

**Metadata and memory**

- Each submit runs heuristic `derive_project_metadata()` from form fields, transcript, and extracted attachment text.
- `merge_derived_metadata()` combines the new snapshot with `session.last_derived_metadata`.
- The structured LLM call receives bounded `conversation_history` plus the full current user prompt (including attachment context).

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/sessions | jq

curl -s -X POST http://127.0.0.1:8000/api/v1/sessions/<session_id>/estimate \
  -H "Content-Type: application/json" \
  -d '{
    "project_name": "Partner portal",
    "project_type": "web_saas",
    "transcript": "Discovery notes: B2B partners need ticket intake, SSO, dashboards, CSV export. Timeline flexible.",
    "target_audience": "b2b_smb",
    "attachments": []
  }' | jq
```

### Estimation path

Every estimate request (v1 markdown, v2 structured, session submit) follows the same pipeline: domain guardrail → optional preprocessing → Jinja2 prompt render (with `detail_level` / `output_format` when the guided form is used) → provider chain. Completion output is capped by `ESTIMATION_OUTPUT_TOKENS_MAX` (default `2048`).

---

## Capabilities

### Domain guardrail

Requests outside the software estimation domain are rejected before reaching the LLM provider:

```json
{
  "detail": {
    "code": "out_of_domain",
    "message": "Only software/project estimation requests are supported."
  }
}
```

Disable with `LLM_DOMAIN_GUARDRAIL_ENABLED=false`.

### Structured API (v2) guardrails

`POST /api/v2/estimate` runs the guarded pipeline: deterministic input checks (prompt injection, basic PII, domain relevance, optional moderation placeholder), a structured LLM call via [Instructor](https://github.com/jxnl/instructor), then lightweight output semantic checks (confidence floor, leakage heuristics).

- Domain mismatches return HTTP `200` with `final_status="degraded"`, `reason_code`, `audit_id`, and `safe_to_cache=false`.
- Enforced unsafe-input policies return HTTP `422` with stable `code` / `audit_id`.
- Rollout overrides per guardrail: `GUARDRAIL_ROLLOUT_*` keys in `.env.example`.

### Semantic cache

Optional vector similarity cache for validated v2 responses. Disabled by default (`SEMANTIC_CACHE_ENABLED=false`).

| Setting | Purpose |
|---------|---------|
| `SEMANTIC_CACHE_REDIS_URL` | Redis Stack endpoint (RediSearch vectors) |
| `SEMANTIC_CACHE_USE_MEMORY_STORE` | Single-process in-memory store for local tests |
| `SEMANTIC_CACHE_SIMILARITY_THRESHOLD` | Minimum cosine similarity for a cache hit (default `0.92`) |
| `SEMANTIC_CACHE_LOG_ONLY` | Log would-be hits without serving cached responses |

See `.env.example` and [docs/technical/README.md](docs/technical/README.md) for the full variable set.

### Actor-Critic-Boss (ACB) orchestration

Optional **multi-LLM quality loop** for session estimates only (`POST /api/v1/sessions/{id}/estimate`). Default **off** (`ACB_ENABLED=false`).

Each active request runs **Actor → Critic → Boss** (up to `ACB_MAX_ITERATIONS` Actor passes). Semantic cache serve is bypassed when ACB is on.

| Setting | Default | Purpose |
|---------|---------|---------|
| `ACB_ENABLED` | `false` | Global kill switch |
| `ACB_ENABLED_ENDPOINTS` | `session_estimate` | Endpoint allowlist |
| `ACB_MAX_ITERATIONS` | `2` | Max Actor passes per request |
| `ACB_FORCE_ENABLED_IN_DEV` | `false` | Force on when `APP_ENV=local` and `DEV_MODE=true` |

Per-request override on session submit: `"orchestration": "acb" | "single_pass" | "default"`.

With `DEV_MODE=true`, the response includes `estimate.acb_trace` (iteration decisions and timings). See [docs/technical/actor-critic-boss-orchestration.md](docs/technical/actor-critic-boss-orchestration.md).

### Observability

Optional Langfuse export via OpenTelemetry. Off by default (`OTEL_EXPORT_ENABLED=false`).

```bash
# Minimal local setup (see .env.example for all keys)
OTEL_EXPORT_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

Traces cover v2 estimation requests with configurable input/output capture (`LANGFUSE_CAPTURE_INPUTS`, `LANGFUSE_CAPTURE_OUTPUTS`).

---

## Configuration

Copy `.env.example` for the full list. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Required for OpenAI provider |
| `ANTHROPIC_API_KEY` | — | Required for Anthropic provider |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model id |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Anthropic model id |
| `DEFAULT_LLM_MODEL` | `openai/gpt-4o-mini` | LiteLLM-style canonical model reference |
| `LLM_PROVIDERS` | `openai,anthropic` | Ordered fallback chain |
| `LLM_AUTH_FALLBACK` | `false` | Treat auth failures as fallback instead of `503` |
| `STATIC_FALLBACK_ENABLED` | `true` | Append deterministic local fallback when all providers fail |
| `LLM_DOMAIN_GUARDRAIL_ENABLED` | `true` | Reject out-of-domain requests before provider calls |
| `ESTIMATION_OUTPUT_TOKENS_MAX` | `2048` | Max completion tokens for estimation calls |
| `DEV_MODE` | `false` | Include provider, timing, versions, and usage in responses |
| `FRONTEND_ORIGINS` | *(local defaults)* | Comma-separated allowed CORS origins |
| `ESTIMATION_OUTPUT_PERSIST_ENABLED` | `false` | Save successful outputs to `output-responses/` |
| `LLM_CALL_PERSIST_ENABLED` | `false` | Save each LLM call request/response as JSON in `output-responses/` |
| `ESTIMATION_STATS_LOG_ENABLED` | `false` | Append NDJSON usage metadata to `output-stats/` |
| `MAX_ATTACHMENT_SIZE_BYTES` | `10485760` | Decoded attachment size cap (session submit) |
| `ALLOWED_ATTACHMENT_MIME_TYPES` | see `.env.example` | Allowed MIME types for attachments |
| `GUARDRAIL_ROLLOUT_*` | *(empty)* | Per-guardrail rollout override (`disabled`, `log_only`, `enforce`) |
| `SEMANTIC_CACHE_*` | see `.env.example` | Semantic cache for v2 (defaults: off / log-only) |
| `ACB_*` | see `.env.example` | Actor-Critic-Boss session orchestration (default: off) |
| `OTEL_*` / `LANGFUSE_*` | see `.env.example` | Observability export (defaults: off) |

Chat completions go through **LiteLLM**. Use short model ids in `OPENAI_MODEL` / `ANTHROPIC_MODEL` (prefixes are added automatically), or set a fully qualified id in `DEFAULT_LLM_MODEL`.

---

## Project structure

```text
master-ia/
├── app/
│   ├── main.py                 # FastAPI entrypoint, lifespan, router registration
│   ├── config.py               # pydantic-settings (typed env configuration)
│   ├── cors.py                 # CORS configuration
│   ├── database.py             # Async SQLAlchemy engine/session (Postgres + pgvector)
│   ├── routers/                # HTTP boundaries (v1, v2, sessions, embeddings, search)
│   ├── middleware/             # HTTP middleware (LLM-call audit)
│   ├── services/               # CAG, LLM chain, sessions, semantic cache, observability
│   ├── guardrails/             # Input/output policy pipeline (+ ACB policy)
│   ├── schemas/                # Pydantic request/response models
│   ├── models/                 # SQLAlchemy ORM models (documents, chunks)
│   ├── context/                # Few-shot example pools
│   ├── embedding_pipeline/     # Budget chunking, embeddings, semantic search (isolated)
│   ├── prompts/                # Jinja2 bundles: estimation/ (v1, v2) and acb/
│   └── scripts/                # In-package CLIs (compare, ingest_from_dir, preflight, …)
├── web/                        # React + Vite + TypeScript UI
├── tests/                      # pytest suite (mocked providers); includes tests/evals/
├── evals/                      # CAG stress harness (evals/stress/)
├── alembic/                    # Database migrations (alembic.ini at repo root)
├── docs/
│   ├── technical/README.md     # Extended architecture, flows, troubleshooting
│   ├── evals/                  # Session eval pyramid documentation
│   └── work-items/             # Implementation specs and ADRs
├── api-collection/             # OpenCollection/Bruno manual requests
├── dev-tools/                  # Provider ping scripts, fixture ingest helpers
├── scripts/                    # Repo-level dev utilities (prompt dump, doc sync)
├── query_examples.py           # Semantic search demo script
├── output-responses/           # Persisted estimation/LLM outputs (opt-in)
├── output-stats/               # NDJSON usage metadata (opt-in)
├── Dockerfile                  # API image
├── Dockerfile.web              # Web (nginx) image
├── docker-compose.yml          # app + web + redis + redisinsight + postgres
├── docker-compose.dev.yml      # Dev override (API live-reload, bind mounts)
├── conftest.py                 # Shared pytest config (heavy-test deselection)
├── .env.example
├── pyproject.toml
└── uv.lock
```

---

## Tests

Run the **default fast suite** (unit + integration with mocked providers; **slow/heavy tests deselected**):

```bash
uv run pytest
```

Heavy tests (`slow` marker: eval soft/judge multi-run, live LLM smoke) are **not** collected unless you opt in:

```bash
# All heavy tests (requires credentials where applicable)
uv run pytest --run-heavy -m slow

# Same via environment variable
RUN_HEAVY_TESTS=1 uv run pytest -m slow

# Full suite including heavy
uv run pytest --run-heavy
```

Run with verbose output:

```bash
uv run pytest -v
```

Run inside a Docker dev container:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm app uv run pytest
```

**Frontend unit tests:**

```bash
cd web && npm run test
```

### Integration tests (sessions)

Session memory, metadata re-injection, attachments, and sliding-window history use the real FastAPI app with `complete_structured` faked (no network):

```bash
uv run pytest tests/test_sessions_integration.py
uv run pytest tests/test_sessions_acb_integration.py -q
```

Ensure `SESSION_INTEGRATION_TEST_USE_REAL_LLM=false` (default) so ACB integration tests use the fake LLM harness.

| Variable | Default | Purpose |
|----------|---------|---------|
| `SESSION_INTEGRATION_TEST_LLM_MODEL` | _(empty → `OPENAI_MODEL`)_ | Model id recorded on fake calls |
| `SESSION_INTEGRATION_TEST_USE_REAL_LLM` | `false` | When `true`, calls real OpenAI (`OPENAI_API_KEY` required); only smoke test runs |

Example — live smoke against OpenAI (costs tokens; not for CI):

```bash
SESSION_INTEGRATION_TEST_USE_REAL_LLM=true \
SESSION_INTEGRATION_TEST_LLM_MODEL=gpt-4o-mini \
OPENAI_API_KEY=sk-... \
uv run pytest --run-heavy tests/test_sessions_integration.py::test_estimate_submit_live_llm_smoke -v
```

### Evaluation suite (session quality pyramid)

Maintainable evals for estimate **quality** and **context use** on the session endpoint. See [docs/evals/session-estimation-evals.md](docs/evals/session-estimation-evals.md).

```bash
# Hard deterministic layer — no API keys
uv run pytest tests/evals -m "evals and not slow"

# Judge layer — live estimator + judge (costs tokens)
EVAL_ESTIMATOR_USE_REAL_LLM=true EVAL_JUDGE_API_KEY=sk-... uv run pytest -m judge
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `EVAL_ESTIMATOR_USE_REAL_LLM` | `false` | Real structured LLM for soft/judge evals |
| `EVAL_ESTIMATOR_MODEL` | _(empty → `OPENAI_MODEL`)_ | Estimator override |
| `EVAL_JUDGE_PROVIDER` | `openai` | Judge provider |
| `EVAL_JUDGE_MODEL` | `gpt-4o-mini` | Judge model |
| `EVAL_JUDGE_API_KEY` | _(empty)_ | Judge key (falls back to provider key) |
| `EVAL_JUDGE_THRESHOLD_MODE` | `warn` | `strict` fails sub-threshold judge scores |

**Coverage highlights:** prompt construction, adaptive routing, guardrails, semantic cache (mocked Redis), session multipart uploads, attachment text extraction (PDF/DOCX built in-process), session eval golden dataset.

### CAG stress testing

Instrumented stress runs for the session CAG baseline (multi-turn scenarios, attachment sizes, deterministic budgets). See [evals/stress/README.md](evals/stress/README.md).

```bash
# Unit tests (no API keys)
uv run pytest tests/test_stress_metrics.py tests/test_stress_scenarios.py

# Regenerate PDF fixtures
uv run python -m evals.stress.fixtures.build_pdfs

# End-to-end against local uvicorn (requires OPENAI_API_KEY)
uv run python -m evals.stress.run \
  --http http://localhost:8000 \
  --scenarios growing,pivot,contradiction \
  --attachment-sizes 0,5,20,50,100 \
  --repeats 3 \
  --write-report
```

Deliverables (per scenario): `evals/stress/results-<scenario>.csv` (one row per turn) and `evals/stress/REPORT-<scenario>.md` (summary tables + interpretation). The default configuration runs ~600 LLM calls per scenario sequentially; use `--turn-counts` and `--repeats` to shorten smoke runs.

### Embedding pipeline

Isolated module under `app/embedding_pipeline/` for budget JSON chunking, OpenAI embeddings, and semantic search over a Postgres corpus. It does **not** share code with the semantic cache (`app/services/semantic_cache/`).

The pipeline includes:

- **Schemas** (`app/embedding_pipeline/schemas.py`) — Pydantic models for budgets, chunks, ingest, and search.
- **Chunker** (`chunker.py`) — `JSONStructuralChunker` produces one chunk per budget component with parent-budget context and tiktoken-based `token_count`.
- **Embedder** (`embedder.py`) — `OpenAIEmbedder` calls `text-embedding-3-small` (1536 dims) with batched requests, rate-limit retry, and cost tracking.
- **Persistence** — Postgres 16 + pgvector, async SQLAlchemy (`app/database.py`), `documents` / `chunks` tables, Alembic migrations. Ingest runs in a single transaction via `run_persistent_ingest()` (`persistent_ingest.py`).
- **Search** (`app/routers/search.py`) — `POST /api/v1/search` embeds the query and ranks chunks by pgvector **cosine distance**.
- **Retrieval debug** (`app/routers/retrieval_debug.py`) — internal `POST /api/v1/retrieval-debug` and `GET /api/v1/retrieval-debug/chunks/{id}` expose vector-branch ranks, normalized scores, explanations, timings, metadata, and chunk context without changing `/search`.
- **Tooling** — upstream loader/parser, markdown chunk template, offline CLIs, `query_examples.py` demo script ([`output_examples.txt`](output_examples.txt)).

Full setup, verification, and design rationale: [Semantic search with pgvector](#semantic-search-with-pgvector).

Optional env (defaults work without extra config):

| Variable | Default | Purpose |
|----------|---------|---------|
| `EMBEDDING_PIPELINE_MODEL` | `text-embedding-3-small` | Embedding model for ingest |
| `EMBEDDING_PIPELINE_BATCH_SIZE` | `100` | Chunks per API request in `embed_many` |
| `DATABASE_URL` | *(empty)* | Async Postgres DSN (`postgresql+asyncpg://...`); set automatically in Compose for `app` |
| `API_BASE_URL` | `http://127.0.0.1:8000` | Base URL for `query_examples.py`; Compose sets `http://app:8000` for the `app` service |

Uses `OPENAI_API_KEY` and `OPENAI_TIMEOUT_SECONDS` (same as chat). Methods are async (`embed_one`, `embed_many`); the compare CLI wraps them with `asyncio.run`.

Chunk contract:

- `chunk_id`: `{budget_id}::{component_id}` (e.g. `BUD-2024-014::AUTH-001`).
- `text`: markdown sections (`## Project context`, `## Component`, `### Tech stack`, `### Estimate`).
- `metadata`: seven component/budget keys plus lineage defaults (`source_name`, `source_version`, `location`) for inline HTTP ingest.

**Ingest endpoint** (`POST /api/v1/embeddings/ingest`):

| Field | Type | Notes |
|-------|------|-------|
| Request `source_path` | `str` | Unique document key (e.g. `data/budgets/budget_2024_q1.json`) |
| Request `document_type` | `str` | e.g. `historical_budget` |
| Request `content` | `Budget` | Same shape as chunker input (one budget per request) |
| Request `metadata` | `dict` | Optional JSON metadata stored on `documents` |
| Response `document_id` | `int` | Postgres `documents.id` |
| Response `chunks_created` | `int` | Rows inserted in `chunks` (0 when `content.components` is empty) |
| Response `embedding_dimension` | `int` | `1536` for `text-embedding-3-small` |
| Response `ingestion_time_ms` | `int` | Wall-clock ingest duration |

Status codes: `200` success, `409` duplicate `source_path` (`{"detail":"Document already ingested","document_id":…}`), `422` validation error, `503` when `DATABASE_URL` is unset, `500` generic failure (details logged server-side).

Requires `DATABASE_URL` for the HTTP endpoint. Document + chunks + embeddings commit atomically; embedder is not called on duplicate `source_path` or zero-component budgets.

```bash
# Local (Postgres must be running; see Postgres section below)
uv run uvicorn app.main:app --reload
# POST http://127.0.0.1:8000/api/v1/embeddings/ingest

# Docker
docker compose up app
# POST http://localhost:8000/api/v1/embeddings/ingest

# Example body
curl -sS -X POST http://127.0.0.1:8000/api/v1/embeddings/ingest \
  -H 'Content-Type: application/json' \
  -d '{"source_path":"data/budgets/bud-2024-014.json","document_type":"historical_budget","content":{...}}'
```

**Search endpoint** (`POST /api/v1/search`):

| Field | Type | Notes |
|-------|------|-------|
| Request `query` | `str` | Non-empty after trim |
| Request `k` | `int` | Default `5`, min `1`, max `50` |
| Response `query` | `str` | Echo of normalized query |
| Response `k` | `int` | Applied limit |
| Response `search_time_ms` | `int` | Wall-clock search duration |
| Response `results[]` | list | Ranked by ascending `distance` |
| Result `chunk_id` | `int` | Postgres `chunks.id` |
| Result `document_id` | `int` | Parent document |
| Result `chunk_type` | `str` | e.g. `budget_component` |
| Result `content` | `str` | Chunk text |
| Result `distance` | `float` | pgvector cosine distance (lower = closer) |
| Result `metadata` | `dict` | JSON metadata from `chunks.metadata` |

Status codes: `200` success (empty corpus returns `results: []`), `422` validation error, `503` when `DATABASE_URL` is unset, `500` generic failure (details logged server-side). Chunks with `embedding IS NULL` are excluded from ranking.

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"REST API with OAuth authentication for fintech sector","k":5}'
```

**Reading search results:** `distance` is pgvector cosine distance — **lower is more similar**. Values around 0.2–0.4 often indicate a strong match on this corpus; 0.65+ suggests moderate similarity. Semantic search is not keyword search: a query mentioning SAML may rank OAuth chunks highly if the corpus has no SAML text but shares “authentication” and “API” signals. See [`output_examples.txt`](output_examples.txt) and [Semantic search with pgvector](#semantic-search-with-pgvector) for worked examples.

**Internal retrieval debug API** (`POST /api/v1/retrieval-debug`, `GET /api/v1/retrieval-debug/chunks/{id}`):

- `POST /api/v1/retrieval-debug` accepts `query`, `strategies` (currently `vector`, future branches return `null` + warning), `vector.top_k`, optional `vector.threshold`, and `max_results`.
- `branches.vector[]` exposes raw vector rank, `distance`, and normalized `score = max(0, min(1, 1 - distance))`; `final_results[]` adds title, excerpt, metadata, source strategies, and explanation signals (`semantic_strong`, `semantic_weak`, `below_threshold`).
- `GET /api/v1/retrieval-debug/chunks/{id}` returns full chunk content, previous/next chunk context, parent document metadata, embedding model, and `embedding_present`; optional `?query=` adds distance/similarity for that single chunk.
- Status codes: `200` success, `404` unknown chunk, `422` invalid request, `503` when `DATABASE_URL` is unset, `500` generic failure. Success logs emit `retrieval_debug_completed` with safe metadata only.

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/retrieval-debug \
  -H 'Content-Type: application/json' \
  -d '{"query":"JWT refresh token rotation for OAuth2 REST API","strategies":["vector"],"vector":{"top_k":20,"threshold":0.6},"max_results":10}' \
  | python3 -m json.tool

curl -sS "http://127.0.0.1:8000/api/v1/retrieval-debug/chunks/156?query=OAuth%20backend" \
  | python3 -m json.tool
```

**Cosine similarity CLI** (`app/scripts/compare.py`): embed two texts with `OpenAIEmbedder.embed_one()` (via `asyncio.run`) and print cosine similarity computed with stdlib `math` only. Results for three reference pairs are recorded in [`app/embedding_pipeline/SANITY_CHECK.md`](app/embedding_pipeline/SANITY_CHECK.md).

```bash
# Outside container (loads .env via pydantic-settings)
uv run python -m app.scripts.compare \
  --text-a "OAuth 2.0 authentication backend for fintech" \
  --text-b "JWT-based authorization service for banking app"

# Inside Docker (service name: app)
docker compose exec app python -m app.scripts.compare \
  --text-a "OAuth 2.0 authentication backend for fintech" \
  --text-b "JWT-based authorization service for banking app"
```

**Pipeline verification (offline):**

```bash
uv run pytest tests/embedding_pipeline/test_milestone_e2e.py
uv run pytest tests/embedding_pipeline/
```

**Upstream ingest from directory:**

```bash
uv run python -m app.scripts.ingest_from_dir \
  --dir tests/embedding_pipeline/fixtures/budget_files --dry-run

uv run python -m app.scripts.ingest_from_dir \
  --dir tests/embedding_pipeline/fixtures/budget_files
```

**Batch ingest fixtures over HTTP (Postgres + API required):**

```bash
uv run python dev-tools/ingest_budget_fixtures.py
uv run python dev-tools/ingest_budget_fixtures.py --skip-existing --dry-run
```

**Ops / learning CLIs:**

```bash
uv run python -m app.scripts.preflight_embedding_pipeline --skip-key-check
uv run python -m app.scripts.inspect_fixtures \
  --dir tests/embedding_pipeline/fixtures/budget_files
uv run python -m app.scripts.architecture_decision --corpus-tokens 5000 --refresh-days 60
```

Optional heavy smoke (real API key): `uv run pytest -m slow tests/embedding_pipeline/ --run-heavy`

**Postgres + migrations:**

```bash
# Start Postgres only
docker compose up -d postgres

# Connection check (manual baseline before app writes)
docker compose exec postgres psql -U estimator -d estimator -c "SELECT version();"

# Apply schema from host (set DATABASE_URL or export from .env)
export DATABASE_URL=postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator
uv run alembic upgrade head

# Inspect tables
docker compose exec postgres psql -U estimator -d estimator -c "\dt"
```

From the `app` container, `DATABASE_URL` is pre-set to `postgresql+asyncpg://estimator:estimator@postgres:5432/estimator`. Roll back with `uv run alembic downgrade base` when you need a clean slate on a dev database.

For Postgres setup, ingest, search, and the query demo script, see [Semantic search with pgvector](#semantic-search-with-pgvector).

---

## Semantic search with pgvector

Persist budget embeddings in Postgres and retrieve them with `POST /api/v1/search`. Captured demo output: [`output_examples.txt`](output_examples.txt).

### Dependencies

| Layer | What you need |
|-------|----------------|
| **Docker** | Compose v2; services `postgres` (`pgvector/pgvector:pg16`) and `app` |
| **Python** | 3.11 + [uv](https://docs.astral.sh/uv/); run `uv sync --group dev` from the repo root |
| **Runtime packages** | `sqlalchemy`, `asyncpg`, `pgvector`, `alembic`, `greenlet` (see `pyproject.toml`) |
| **Environment** | `OPENAI_API_KEY` (ingest + search embed calls), `DATABASE_URL` (host/local), optional `EMBEDDING_PIPELINE_MODEL`, `API_BASE_URL` |

Compose sets `DATABASE_URL=postgresql+asyncpg://estimator:estimator@postgres:5432/estimator` and `API_BASE_URL=http://app:8000` on the `app` service. See `.env.example` for placeholders.

### Initial setup and startup

```bash
# 1. Environment
cp .env.example .env
# Set OPENAI_API_KEY — required for ingest and search (real embedding calls)

# 2. Install Python deps (local CLI: alembic, ingest helper, query_examples)
uv sync --group dev

# 3. Start Postgres + API
docker compose up --build -d postgres app

# 4. Apply schema (from host; matches Compose credentials)
export DATABASE_URL=postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator
uv run alembic upgrade head

# 5. Health check
curl -s http://127.0.0.1:8000/health
docker compose exec postgres psql -U estimator -d estimator -c "SELECT version();"
```

**Local API without Docker** (Postgres must still be reachable):

```bash
docker compose up -d postgres
export DATABASE_URL=postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

### Verify each component

**Database schema (Postgres + pgvector)**

```bash
uv run alembic upgrade head
docker compose exec postgres psql -U estimator -d estimator -c "\dt"   # documents, chunks
uv run pytest tests/test_database_models.py tests/test_alembic_migration.py -q
```

**Persistent ingest** (`POST /api/v1/embeddings/ingest`)

```bash
# Batch ingest all budget fixtures (real OpenAI calls for budgets with components)
uv run python dev-tools/ingest_budget_fixtures.py --skip-existing

# Inspect persisted rows
docker compose exec postgres psql -U estimator -d estimator \
  -c "SELECT count(*) AS documents FROM documents; SELECT count(*) AS chunks FROM chunks;"

# Re-run the same fixture → HTTP 409 (duplicate source_path)
uv run python dev-tools/ingest_budget_fixtures.py --skip-existing

uv run pytest tests/embedding_pipeline/test_persistent_ingest_service.py tests/embedding_pipeline/test_router.py -q
```

Single-document `curl` example (replace `content` with a full budget JSON from `tests/embedding_pipeline/fixtures/budget_files/`):

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/embeddings/ingest \
  -H 'Content-Type: application/json' \
  -d '{"source_path":"data/budgets/bud-2024-014.json","document_type":"historical_budget","content":{"budget_id":"BUD-2024-014","client_metadata":{"name":"FintechCorp","sector":"finance","country":"ES"},"project_summary":"Mobile banking API with OAuth 2.0 authentication","main_technology":"ruby_on_rails","year":2024,"total_estimated_hours":120,"components":[]}}'
```

**Semantic search** (`POST /api/v1/search`)

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"REST API with OAuth authentication for fintech sector","k":5}' \
  | python3 -m json.tool

uv run pytest tests/embedding_pipeline/test_search_*.py -q
```

Read `distance` as cosine distance: **lower = more similar** (~0.2–0.4 strong on this corpus; ~0.65+ moderate).

**Retrieval debug** (`POST /api/v1/retrieval-debug`, `GET /api/v1/retrieval-debug/chunks/{id}`)

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/retrieval-debug \
  -H 'Content-Type: application/json' \
  -d '{"query":"REST API with OAuth authentication for fintech sector","strategies":["vector"],"vector":{"top_k":10},"max_results":5}' \
  | python3 -m json.tool

curl -sS "http://127.0.0.1:8000/api/v1/retrieval-debug/chunks/156?query=OAuth%20backend" \
  | python3 -m json.tool

uv run pytest tests/embedding_pipeline/test_retrieval_debug_*.py -q
```

Use this internal API to explain vector retrieval: `distance` remains raw cosine distance, `score` is normalized similarity, `source_strategies` is `["vector"]` in feature-042, and non-vector branches are intentionally `null` until later retrieval sub-features.

**Query demo script** (`query_examples.py`)

```bash
uv run python query_examples.py --base-url http://127.0.0.1:8000
docker compose run --rm app python query_examples.py
docker compose run --rm --no-TTY app python query_examples.py > output_examples.txt

uv run pytest tests/embedding_pipeline/test_query_examples.py -q
```

**Offline regression (no live API / OpenAI):**

```bash
uv run pytest tests/embedding_pipeline/ -q
```

### Design rationale

**(a) Two tables (`documents` + `chunks`), not one flat table**

A single table mixing document fields and chunk rows would duplicate `source_path`, `document_type`, and ingest timestamps on every chunk, complicate duplicate detection, and make deletes error-prone. Splitting keeps **document-level identity** (`source_path` uniqueness, optional document metadata) separate from **retrieval units** (chunk text + embedding). `ON DELETE CASCADE` from `documents` to `chunks` guarantees that removing a source document never leaves orphan vectors.

**(b) JSONB metadata instead of typed columns**

Budget components expose varying keys (`client_sector`, `tech_stack`, `complexity`, …). Modeling each as a SQL column would require a migration for every new field and produce wide sparse tables. **JSONB** stores the chunker’s structured metadata as-is, accepts evolution without schema churn, and still allows a **GIN index** on `chunks.metadata` when metadata filters are added later. Typed columns would be justified in production when a small set of filter fields is stable and query-critical.

**(c) `cosine_distance`, not L2 or inner product**

OpenAI embedding vectors are commonly compared by **cosine similarity** in RAG pipelines: ranking depends on direction in embedding space, not vector magnitude. pgvector exposes this as the `<=>` operator via `embedding.cosine_distance()`. **L2 (Euclidean) distance** would penalize magnitude differences and can reorder results when vectors are not normalized the same way. **Inner product** (`<#>`) assumes a different geometry and pairs with a different index operator class. Choosing cosine aligns search ranking with common RAG practice and a future **HNSW index with `vector_cosine_ops`** without changing the metric later.

**(d) HNSW index on `chunks.embedding`**

Feature-036/038 deliberately used a **sequential scan** baseline to measure latency and teach query-plan inspection on a small corpus (~tens of chunks). Feature-040 adds **`ix_chunks_embedding_hnsw`** with **`vector_cosine_ops`**, matching the existing `cosine_distance` search SQL without API changes. On very small tables the planner may still choose sequential scan until statistics favour ANN — verify with `EXPLAIN` and `scripts/pgvector_observability.sql` (see [docs/technical/README.md §24](docs/technical/README.md#24-hnsw-vector-index-feature-040)).

### Out of scope

Metadata filters, hybrid keyword + vector search, ranking benchmarks, and retrieval tuning are **not** implemented here.

Further detail: [docs/technical/README.md §22–§24](docs/technical/README.md).

---

## Documentation

| Resource | Description |
|----------|-------------|
| [Semantic search with pgvector](#semantic-search-with-pgvector) | Setup, component verification, design rationale |
| [docs/technical/README.md §22](docs/technical/README.md#22-postgres-pgvector-baseline-feature-036) | Postgres pgvector: schema, migrations, manual verification, GUI clients |
| [docs/technical/README.md §23](docs/technical/README.md#23-semantic-search-endpoint-feature-038) | Search endpoint contract and module layout |
| [docs/technical/README.md §24](docs/technical/README.md#24-hnsw-vector-index-feature-040) | HNSW index, observability SQL, query-plan checks |
| [docs/evals/session-estimation-evals.md](docs/evals/session-estimation-evals.md) | Session eval pyramid: goldens, hard/soft/judge runs, calibration |
| [web/README.md](web/README.md) | Frontend setup, scripts, theming |
| [api-collection/](api-collection/) | Manual HTTP requests (OpenCollection/Bruno) |
| `.env.example` | Complete environment variable reference with inline comments |

For the v1 Markdown + SSE contract details, see [docs/technical/README.md §11](docs/technical/README.md#11-api-contract).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Startup error: *No provider could be configured…* | No API keys and static fallback disabled | Add `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` to `.env`, or set `STATIC_FALLBACK_ENABLED=true` |
| `503` with auth/configuration message | Invalid or missing API key | Verify keys and model names; or set `LLM_AUTH_FALLBACK=true` for auth fallback |
| `422` on v1 estimate | Missing or empty required fields | Check request body against `/docs` schema |
| CORS error from web UI | Origin not allowed | Add dev URL to `FRONTEND_ORIGINS` in `.env` |
| Semantic cache never hits | Cache disabled or log-only | Set `SEMANTIC_CACHE_ENABLED=true`, configure Redis URL, set `SEMANTIC_CACHE_LOG_ONLY=false` |
| `/favicon.ico` returns `404` | No favicon served by API | Expected — browsers request it automatically |

More detail: [docs/technical/README.md §20](docs/technical/README.md#20-troubleshooting).

---

## Security

- **Never commit `.env`** — it is gitignored; `.env.example` holds placeholders only.
- API keys are read from environment variables via `pydantic-settings`.
- Logs must not include credentials, tokens, or full user transcripts.
- The default test suite does not require real provider keys.
- Session state is **in-memory only** — not suitable for multi-instance production without external storage.
- Guardrails reduce risk but are not a substitute for production content moderation or auth.

---

**Status:** Active development · **Version:** `0.1.0` (see `pyproject.toml`)
