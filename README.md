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
| **API hardening** | Optional `X-API-Key` on retrieval and RAG estimate routes, opt-in per-key rate limits, global `X-Request-ID` correlation. |
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

**Grounded RAG citations** (feature-052): the estimate result panel includes **Run RAG estimate**, which calls `POST /api/v1/estimate/rag` with the one-line summary + transcript as the retrieval question. Results appear on the **RAG citations** tab: per-line `component`, `hours`, `grounded`, `rationale`, `sources[]`, plus a `citation_summary` audit strip (`grounded_ok`, `dangling`, `insufficient`, `integrity_violations`). This path is separate from the CAG v2 session estimate (no semantic cache / ACB).

The internal retrieval debug screen lives at `/debug/retrieval` and is hidden unless `VITE_ENABLE_RETRIEVAL_DEBUG=true`. It consumes the debug API to compare vector, lexical, hybrid, and rerank lanes, tune request knobs, render ranking diffs and explanation chips, and inspect chunk context in a drawer. Keep the flag disabled for normal end-user builds.

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

```bash
cd web
VITE_ENABLE_RETRIEVAL_DEBUG=true npm run dev
# Open http://127.0.0.1:5173/debug/retrieval
```

When using Docker Compose, rebuild the web image with the flag enabled because Vite env variables are baked into the static bundle:

```bash
VITE_ENABLE_RETRIEVAL_DEBUG=true docker compose up -d --build web
# Open http://127.0.0.1:5175/debug/retrieval
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
| `POST` | `/api/v1/retrieval` | Production retrieval modes A/B/C/D (vector, hybrid RRF, rerank); optional `X-API-Key` when `RETRIEVAL_API_KEY` is set |
| `POST` | `/api/v1/retrieval/advanced` | StageConfig-driven advanced retrieval (S10 parity); presets A–D or explicit config; optional `X-API-Key` when `RETRIEVAL_API_KEY` is set |
| `POST` | `/api/v1/estimate/rag` | Grounded RAG estimation with citation audit; optional `X-API-Key` when `ESTIMATE_API_KEY` is set |
| `POST` | `/api/v1/estimate/agent` | Session 12 agentic loop (transcript → estimate + trace); requires `OPENAI_API_KEY`; uses `DATABASE_URL` for real retrieval |
| `POST` | `/api/v1/retrieval-debug` | Internal vector/lexical/hybrid retrieval debug with optional metadata filters |
| `GET`/`PUT` | `/api/v1/config/retrieval` | Runtime retrieval config (Redis override merged over `Settings`); open in dev |
| `GET`/`PUT` | `/api/v1/config/models` | Runtime model config (`structured_model`, `judge_model`); open in dev |

The `embeddings/ingest`, `search`, `retrieval`, `estimate/rag`, and `estimate/agent` endpoints belong to the isolated [embedding pipeline](#semantic-search-with-pgvector) / agent retrieval path and require `DATABASE_URL` (except agent CLI with `--stub`).

Every HTTP response includes an **`X-Request-ID`** header (client-supplied values are echoed). See [API hardening](#api-hardening-retrieval--rag).

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
| `RETRIEVAL_API_KEY` | *(empty)* | When set, `POST /api/v1/retrieval` requires matching `X-API-Key` |
| `ESTIMATE_API_KEY` | *(empty)* | When set, `POST /api/v1/estimate/rag` requires matching `X-API-Key` (not applied to `/estimate/agent`) |
| `AGENT_MODEL` | `gpt-5-mini` | Default model for Session 12 agentic loop |
| `AGENT_REASONING_EFFORT` | `medium` | Responses API reasoning effort for agent (`minimal` \| `low` \| `medium` \| `high`) |
| `AGENT_MAX_ITERATIONS` | `10` | Hard cap on agent Responses API round-trips |
| `AGENT_RETRIEVAL_MODE` | *(empty)* | Retrieval mode for agent `search_budgets`; empty uses `RAG_ESTIMATION_RETRIEVAL_MODE` |
| `RATE_LIMIT_ENABLED` | `false` | When `true`, limits retrieval to 120/min and RAG estimate to 10/min per API-key bucket (IP fallback) |
| `REDIS_URL` | *(empty)* | Generic Redis DSN for `GET/PUT /api/v1/config/*` runtime overrides; empty falls back to env `Settings` |

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
│   ├── routers/                # HTTP boundaries (v1, v2, sessions, embeddings, search, agent)
│   ├── middleware/             # HTTP middleware (request ID, rate limits, LLM-call audit)
│   ├── services/               # CAG, LLM chain, sessions, semantic cache, agentic, observability
│   │   ├── agentic/            # Session 12: agent loop, tools, retrieval adapter (feature-054)
│   │   └── estimation_graph/   # Session 13: LangGraph multi-agent estimation (feature-066)
│   ├── guardrails/             # Input/output policy pipeline (+ ACB policy)
│   ├── schemas/                # Pydantic request/response models
│   ├── models/                 # SQLAlchemy ORM models (documents, chunks)
│   ├── context/                # Few-shot example pools
│   ├── embedding_pipeline/     # Budget chunking, embeddings, semantic search (isolated)
│   ├── prompts/                # Jinja2 bundles: estimation/ (v1, v2) and acb/
│   └── scripts/                # In-package CLIs (compare, ingest_from_dir, run_agent_s12, run_graph_s13, …)
├── exercises/                  # Session exercise kits (session-12, session-13, …)
├── web/                        # React + Vite + TypeScript UI
├── tests/                      # pytest suite (mocked providers); includes tests/evals/
├── evals/                      # CAG stress harness (evals/stress/)
├── alembic/                    # Database migrations (alembic.ini at repo root)
├── docs/
│   ├── technical/README.md     # Extended architecture, flows, troubleshooting
│   ├── technical/agentic-estimation-loop.md  # Session 12 agent reference (feature-054)
│   ├── technical/estimation-graph-s13.md     # Session 13 LangGraph graph (feature-066)
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

### Parallel feature worktrees

Use `scripts/worktree_tasks.py` to prepare isolated Git worktrees for feature work items without replacing `/start-task`.

```bash
uv run python scripts/worktree_tasks.py plan -f docs/technical/worktree-task-orchestrator.example.yaml
uv run python scripts/worktree_tasks.py prepare -f docs/technical/worktree-task-orchestrator.example.yaml --only 042 --dry-run
uv run python scripts/worktree_tasks.py prepare -f docs/technical/worktree-task-orchestrator.example.yaml --only 042
```

Prepared worktrees are created outside this repository by default (`../master-ia-worktrees`) and include an `INSTRUCTIONS.md` with the manual Cursor command to run inside that worktree. `.env` is symlinked when present; never commit it. Live Postgres/Redis checks should be serialized because the local Compose stack uses shared fixed ports.

Inspect and clean up:

```bash
uv run python scripts/worktree_tasks.py status -f docs/technical/worktree-task-orchestrator.example.yaml
uv run python scripts/worktree_tasks.py cleanup -f docs/technical/worktree-task-orchestrator.example.yaml --only 042 --dry-run
```

The `run --dry-run` command previews the future Cursor SDK runner, but it does not launch agents yet.

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
- **Production retrieval** (`app/routers/retrieval.py`) — `POST /api/v1/retrieval` runs modes **A** vector-only, **B** hybrid RRF, **C** vector + cross-encoder rerank, **D** hybrid + rerank; defaults preserve mode **A** (vector-only baseline).
- **Advanced retrieval** (`app/routers/retrieval_advanced.py`) — `POST /api/v1/retrieval/advanced` runs the S10 `StageConfig` pipeline (`advanced_retrieve`) with presets **A–D** or an explicit config payload; reuses hybrid RRF and rerank primitives; labels every row with `collection` when `RETRIEVAL_ROUTING_ENABLED=true` (multi-index via `chunks.collection`).
- **Chunking compare** (`app/routers/embeddings.py`) — `POST /api/v1/embeddings/compare` compares chunking strategies on sample budgets (stats + optional query preview; no persistence).
- **Multi-index ingest** — `app/scripts/ingest_transcript.py` and `app/scripts/ingest_technical_doc.py` persist transcript and technical-doc segments into `chunks.collection` (`transcripts`, `technical_docs`).
- **Retrieval debug** (`app/routers/retrieval_debug.py`) — internal `POST /api/v1/retrieval-debug` and `GET /api/v1/retrieval-debug/chunks/{id}` expose vector and lexical branch ranks, normalized scores, matched terms, explanations, timings, metadata, and chunk context without changing `/search`.
- **Tooling** — upstream loader/parser, markdown chunk template, offline CLIs, `query_examples.py` demo script ([`output_examples.txt`](output_examples.txt)).

Full setup, verification, and design rationale: [Semantic search with pgvector](#semantic-search-with-pgvector).

Optional env (defaults work without extra config):

| Variable | Default | Purpose |
|----------|---------|---------|
| `EMBEDDING_PIPELINE_MODEL` | `text-embedding-3-small` | Embedding model for ingest |
| `EMBEDDING_PIPELINE_BATCH_SIZE` | `100` | Chunks per API request in `embed_many` |
| `DATABASE_URL` | *(empty)* | Async Postgres DSN (`postgresql+asyncpg://...`); set automatically in Compose for `app` |
| `RETRIEVAL_DEFAULT_MODE` | `A` | Default mode when request omits `mode` (`A|B|C|D`) |
| `RETRIEVAL_LEXICAL_TEXT_SEARCH_CONFIG` | `spanish` | Postgres FTS config for lexical branch |
| `RETRIEVAL_RECALL_K` | `50` | Recall width before fusion/rerank |
| `RETRIEVAL_TOP_K_FINAL` | `5` | Final cut after fusion/rerank |
| `RETRIEVAL_RRF_K` | `60` | RRF constant for hybrid modes |
| `RETRIEVAL_RERANK_ENABLED` | `false` | Global rerank kill switch |
| `RETRIEVAL_RERANK_MODEL` | *(empty)* | Cross-encoder model id; empty ⇒ no-op rerank |
| `RETRIEVAL_ROUTING_ENABLED` | `false` | When `true`, advanced retrieval routes queries to `budgets`, `transcripts`, or `technical_docs` collections |
| `CHUNKING_COMPARE_DEFAULT_STRATEGIES` | `structural,recursive,sentence_window` | Default strategies for `POST /api/v1/embeddings/compare` |
| `CONVERSATION_COMPRESSION_ENABLED` | `false` | Anchor + cumulative summarization on long session histories |
| `TRANSCRIPT_PII_ENABLED` | `false` | Redact PII on transcript ingest CLI (optional `uv sync --group pii`) |
| `QUERY_TRANSFORM_ENABLED` | `false` | When `true`, advanced retrieval may rewrite queries before search (stub passthrough) |
| `RETRIEVAL_TEMPORAL_DECAY_ENABLED` | `false` | When `true`, advanced retrieval may apply recency weighting (no-op until metadata exists) |
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

**Production retrieval API** (`POST /api/v1/retrieval`):

| Field | Type | Notes |
|-------|------|-------|
| Request `query` | `str` | Non-empty reformulated retrieval text |
| Request `mode` | `A\|B\|C\|D` | Optional; defaults to `RETRIEVAL_DEFAULT_MODE` |
| Request `recall_k` | `int` | Optional recall width (default from settings) |
| Request `top_k_final` | `int` | Optional final cut (default from settings) |
| Response `mode` | `str` | Applied mode (may degrade C/D when rerank disabled) |
| Response `applied_config` | `object` | Branches, fusion, rerank flags, timings config |
| Response `timings_ms` | `object` | Per-stage latency (`vector`, `lexical`, `fusion`, `rerank`, `total`) |
| Response `results[]` | list | Lean ranked rows with nullable branch scores |
| Response `warnings` | list | No-op rerank, branch failures, kill-switch notices |

Modes: **A** vector-only (baseline); **B** vector + lexical RRF; **C** vector + cross-encoder rerank; **D** hybrid + rerank. Lexical FTS uses migration `0004` (`content_tsv` generated with `spanish`).

**Advanced retrieval API** (`POST /api/v1/retrieval/advanced`):

| Field | Type | Notes |
|-------|------|-------|
| Request `query` | `str` | Non-empty composed search text (same contract as production retrieval) |
| Request `preset` | `A\|B\|C\|D` | Optional shorthand for `StageConfig` presets (mutually exclusive with `config`) |
| Request `config` | `object` | Optional explicit `StageConfig` (`search_mode`, `rerank`, `fusion`, …) |
| Request `recall_k` / `top_k_final` | `int` | Optional overrides (default from settings) |
| Response `config` / `effective_config` | `object` | Requested vs applied stage config (rerank may degrade) |
| Response `results[]` | list | Ranked rows with `collection` label (`budgets` stub) and branch scores |
| Response `warnings` | list | No-op rerank, branch failures, kill-switch notices |

```bash
# When RETRIEVAL_API_KEY is set in .env, add: -H 'X-API-Key: your-retrieval-key'
curl -sS -X POST http://127.0.0.1:8000/api/v1/retrieval/advanced \
  -H 'Content-Type: application/json' \
  -d '{"query":"OAuth backend integration","preset":"B"}'
```

Preset mapping for eval parity with modes A–D: **A** vector / no rerank; **B** hybrid RRF; **C** vector + rerank; **D** hybrid + rerank. Runtime `PUT /api/v1/config/retrieval` `rerank_enabled` override applies to the advanced path the same way as `POST /api/v1/retrieval`.

**Evaluation harness** (modes A–D over the golden set):

```bash
DATABASE_URL=postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator \
RETRIEVAL_RERANK_ENABLED=true \
RETRIEVAL_RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2 \
RETRIEVAL_RECALL_K=50 \
RETRIEVAL_TOP_K_FINAL=5 \
RETRIEVAL_RRF_K=60 \
uv run python app/scripts/retrieval_eval.py --repetitions 5
```

Requires populated Postgres (Alembic `0004`), `OPENAI_API_KEY`, and a non-no-op reranker for modes C/D. Preflight blocks empty corpus, missing embeddings/`budget_id`, stale Alembic, or no-op reranker. Writes `comparison.md`, `results.json`, and `recommendation.md` under `evaluation/retrieval/results/<timestamp>/`. Committed evidence: `evaluation/retrieval/results/20260623T154959Z/` (mode **B** recommended; rerank did not justify latency on this corpus). See [docs/technical/README.md](docs/technical/README.md) §25c for methodology and interpretation.

**Grounded RAG estimation** (`POST /api/v1/estimate/rag`):

- Separate from CAG v2: no semantic cache, ACB, or v2 output guardrails; basic non-empty input validation only.
- Flow: `reformulate_query` → `compose_search_text` → `RetrievalService.retrieve` → `ChunkContentRepository` re-fetch by `chunk_id` → `truncate_to_token_budget` → Jinja prompts (`estimation/rag/v1`) → `complete_structured` with `RagEstimationResult` → `verify_citations` (chunk membership audit) → `check_coherence` (structural rules) → `gate_estimate` (optional numeric + LLM judge).
- Optional request field `transcript` triggers LLM reformulation; when omitted and `REFORMULATION_ENABLED=false`, retrieval uses the question as-is.
- Response includes per-line `sources`, `grounded`, `citation_summary` counts (`grounded_ok`, `dangling`, `insufficient`, `integrity_violations`), `coherence_summary` (`coherent_ok`, `total_hours_mismatch`, `duplicate_component`, `insufficient_context_violation`, `zero_hours_grounded`, `has_violations`), and `hallucination_summary` (`grounded`, `degraded`, `insufficient`, `has_degraded`).
- Env: `RAG_ESTIMATION_RETRIEVAL_MODE` (default **B**), `RAG_COHERENCE_ENABLED` (default **true**), `RAG_COHERENCE_TOTAL_TOLERANCE` (default **0.01**), `HALLUCINATION_GATE_ENABLED` (default **false**), `HALLUCINATION_JUDGE_MODEL` (optional LiteLLM id), `REFORMULATION_ENABLED` (default **false**), `REFORMULATION_MODEL` (optional LiteLLM id), `RAG_CONTEXT_MAX_TOKENS` (default **8000**), `RAG_IDEMPOTENCY_TTL_SECONDS` (default **86400**); reuses `RETRIEVAL_RECALL_K` / `RETRIEVAL_TOP_K_FINAL`.

```bash
# When ESTIMATE_API_KEY is set in .env, add: -H 'X-API-Key: your-estimate-key'
curl -sS -X POST http://127.0.0.1:8000/api/v1/estimate/rag \
  -H 'Content-Type: application/json' \
  -d '{"question":"Plataforma e-commerce con Stripe y OAuth2","transcript":"Cliente pide login OAuth y pagos Stripe."}'
```

In **`web/`**, fill the transcript (and optional one-line summary), then use **Run RAG estimate** in the estimate result panel and open the **RAG citations** tab to compare the UI table with the JSON payload.

**RAG stage wizard API** (feature-062, stateless teaching endpoints under `/api/v1/estimate/rag/stages/*`):

- `reformulate` → `retrieve` (basic mode A–D or advanced `StageConfig`) → `assemble` → `generate` → `verify` (citation + coherence + hallucination reports).
- `structure` — modules/tasks without hours (Session 10 decomposition).
- `POST /api/v1/estimate/rag/tasks/hours` — per-task hours from `historical_task` chunks (`TASK_HOURS_TOP_K`, `TASK_HOURS_DISTANCE_THRESHOLD`).
- `Idempotency-Key` header on `POST /api/v1/estimate/rag` caches the full response for `RAG_IDEMPOTENCY_TTL_SECONDS` (Redis when `REDIS_URL` set, else in-process).

**Agentic estimation (Session 12)** (`POST /api/v1/estimate/agent`):

- Separate from the fixed RAG pipeline: a **manual** reason → act → observe loop on the OpenAI **Responses API** (`responses.create` / `responses.parse`), not LiteLLM/Instructor.
- Tools: `search_budgets` (wraps `RetrievalService.retrieve` + chunk content), `calculate_estimate` (deterministic median + contingency), `validate_estimate` (optional guardrails).
- Env: `AGENT_MODEL` (default `gpt-5-mini`), `AGENT_REASONING_EFFORT` (`minimal|low|medium|high`), `AGENT_MAX_ITERATIONS` (default `10`), `AGENT_RETRIEVAL_MODE` (empty → `RAG_ESTIMATION_RETRIEVAL_MODE`).
- **Cost discipline:** debug with `gpt-5-mini` + `--stub` on the simple transcript; deliverable run uses `gpt-5` + `medium` on `sample_transcript_complex.txt`.

```bash
# Offline loop debugging (no database)
uv run python app/scripts/run_agent_s12.py \
  exercises/session-12/sample_transcript_simple.txt --model gpt-5-mini --stub

# Deliverable trace file (requires OPENAI_API_KEY; live API cost).
# gpt-5 + medium often needs a longer HTTP timeout than the default 30s:
OPENAI_TIMEOUT_SECONDS=600 uv run python app/scripts/run_agent_s12.py \
  exercises/session-12/sample_transcript_complex.txt --model gpt-5 --effort medium \
  --stub --out /tmp/agent_trace_complex.txt

# HTTP API (requires OPENAI_API_KEY and DATABASE_URL for real retrieval)
curl -sS -X POST http://127.0.0.1:8000/api/v1/estimate/agent \
  -H 'Content-Type: application/json' \
  -d '{"transcript":"..."}'
```

Exercise assets live under `exercises/session-12/`. See [learnings/docs/sesiones/sesion-12-agentic-estimation-loop.md](learnings/docs/sesiones/sesion-12-agentic-estimation-loop.md) and the full technical reference [docs/technical/agentic-estimation-loop.md](docs/technical/agentic-estimation-loop.md).

**Multi-agent estimation graph (Session 13)** (feature-066, LangGraph):

- Explicit graph under `app/services/estimation_graph/`: classifier → structure → human gate → per-task hours fan-out → recovery → analysis → human gate → optional proposal.
- CLI auto-approves both gates. `--memory` uses `MemorySaver` (no Postgres); `--stub` uses canned per-task hours (no DB fan-out). LLM agents still need `OPENAI_API_KEY`.
- HTTP: blocking `POST /api/v1/estimate/graph` (+ `/resume`, `/state`) and live `POST …/stream`, `…/resume-stream`, `GET …/progress`, `POST …/proposal` (auth: `ESTIMATE_API_KEY`). Postgres checkpointer + lifespan → `app.state.graph`.

```bash
# Partial-offline smoke (no Postgres checkpoints; stub hours)
uv run python app/scripts/run_graph_s13.py --memory --stub

# Write a local report (do not commit generated run files)
uv run python app/scripts/run_graph_s13.py --memory --stub \
  --out /tmp/example_run_complex.txt
```

Exercise assets: `exercises/session-13/`. See [learnings/docs/sesiones/sesion-13-langgraph-multi-agent-estimation.md](learnings/docs/sesiones/sesion-13-langgraph-multi-agent-estimation.md) and [docs/technical/estimation-graph-s13.md](docs/technical/estimation-graph-s13.md).

**RAGAS generation baseline** (offline, slow, dev dependency):

```bash
DATABASE_URL=postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator \
OPENAI_API_KEY=... \
RAG_ESTIMATION_RETRIEVAL_MODE=B \
RAGAS_JUDGE_MODEL=gpt-4o-mini \
RAGAS_EMBEDDING_MODEL=text-embedding-3-small \
uv run python app/scripts/ragas_generation_eval.py
```

Golden set: `evaluation/generation/golden_set.json` (5 queries + expert `ground_truth`). Writes `metrics.json`, `comparison.md`, and `quality_note.md` under `evaluation/generation/results/<timestamp>/`. The runner shapes a natural-language RAGAS `answer` via `format_ragas_answer()` (not raw JSON) and serializes non-finite metrics as `null` / `n/a`. Preflight requires populated corpus, Alembic `0004`, importable `ragas`, and `OPENAI_API_KEY`. See [docs/technical/README.md](docs/technical/README.md) §25d.

**RAGAS regression gate and monitor** (feature-055, CI-friendly):

```bash
# Gate: exit 1 on regression vs the committed baseline, exit 0 on pass.
uv run python app/scripts/ragas_generation_eval.py --gate

# Monitor: print a one-line faithfulness/answer relevancy summary (no gating).
uv run python app/scripts/ragas_generation_eval.py --monitor

# Combine, override baseline path and tolerance:
uv run python app/scripts/ragas_generation_eval.py --gate --monitor \
  --baseline evaluation/generation/RAGAS_BASELINE.md --tolerance 0.05

# Also fail when any golden-set estimate has structural coherence violations:
uv run python app/scripts/ragas_generation_eval.py --gate --coherence-gate
```

- `--gate` compares `mean_faithfulness` (and `mean_answer_relevancy` when finite) against `evaluation/generation/RAGAS_BASELINE.md` (or `--baseline`); a metric regresses when `current_mean < baseline_mean - tolerance`.
- `--coherence-gate` (with `--gate`) fails when `coherence_violation_count > 0` in the eval run (`evaluate_coherence_gate` in `generation_eval.py`).
- Exit codes: **0** pass (or no `--gate`), **1** gate regression, **2** preflight/baseline-load error (unchanged preflight semantics, extended to a missing/malformed baseline file).
- `--monitor` never changes the exit code; it only prints a summary line for watch-mode / dashboards.
- Gate/monitor helpers (`load_baseline`, `evaluate_gate`, `render_gate_summary`, `render_monitor_summary` in `app/embedding_pipeline/generation_eval.py`) are pure functions unit-tested with mocked metrics in `tests/embedding_pipeline/test_generation_gate.py`; they do not import `ragas` at collection time. See `evaluation/generation/RAGAS_BASELINE.md` for baseline provenance and update instructions.

```bash
# When RETRIEVAL_API_KEY is set in .env, add: -H 'X-API-Key: your-retrieval-key'
curl -sS -X POST http://127.0.0.1:8000/api/v1/retrieval \
  -H 'Content-Type: application/json' \
  -d '{"query":"API REST con OAuth2 y Stripe","mode":"B"}'
```

**Internal retrieval debug API** (`POST /api/v1/retrieval-debug`, `GET /api/v1/retrieval-debug/chunks/{id}`):

- `POST /api/v1/retrieval-debug` accepts `query`, `strategies` (`vector`, `lexical`, `hybrid`, `rerank`, or `all`), `vector.top_k`, optional `vector.threshold`, `lexical.top_k`, `hybrid.enabled`, `hybrid.method` (`rrf` or `weighted`), optional `hybrid.rrf_k`, `hybrid.weights`, `rerank.enabled` (default `false`), `filters`, and `max_results`.
- `filters` is optional and ignored when empty or `null`. Supported keys: `document_type`, `client_sector`, `main_technology`, `source_name`, `language`, `tags`, and `year`. Provided filters are AND-combined before branch ranking/limiting; unknown keys are ignored, while malformed typed values such as `year.from: "recent"` return `422`.
- Scalar metadata filters use JSONB containment on `chunks.metadata` (`@>`) and can reuse `ix_chunks_metadata_gin`. `document_type` filters join `documents`. `tags` uses contains-all semantics (`chunks.metadata['tags'] @> [...]`). `year.from` / `year.to` are inclusive bounds over numeric `chunks.metadata.year`.
- `branches.vector[]` exposes raw vector rank, `distance`, and normalized `score = max(0, min(1, 1 - distance))`; `branches.lexical[]` uses Postgres `websearch_to_tsquery` against the generated `chunks.content_tsv` column, ranked with `ts_rank_cd`, min-max normalized scores, and deterministic `matched_terms`.
- `branches.hybrid[]` fuses vector and lexical rankings with Reciprocal Rank Fusion by default (`Σ weight/(rrf_k + rank)`) or weighted normalized branch scores. Hybrid `final_results[]` are ordered by `fusion_rank`, include `fusion_score`, semantic/lexical evidence when present, `diff`, and explanation signals (`semantic_strong`, `semantic_weak`, `lexical_exact_match`, `branch_consensus`, `hybrid_rescued`, `below_threshold`).
- `rerank.enabled=true` runs the configured reranker after fusion/branch ordering. The default `NoOpReranker` preserves order, fills `branches.rerank[]`, sets `rerank_rank`, leaves `rerank_score=null`, and emits a warning that rerank is a no-op placeholder. Injected future rerankers can reorder or filter candidates without changing the response contract; promotions/demotions use `rerank_promoted` and `rerank_demoted`.
- `diff` reports `common`, `vector_only`, `lexical_only`, `hybrid_rescued`, `big_movers`, `dropped_by_threshold`, and `dropped_by_rerank`. The lexical branch keeps the same response contract after the indexed `content_tsv` migration.
- `GET /api/v1/retrieval-debug/chunks/{id}` returns full chunk content, previous/next chunk context, parent document metadata, embedding model, and `embedding_present`; optional `?query=` adds distance/similarity and single-chunk lexical `matched_terms`.
- Status codes: `200` success, `404` unknown chunk, `422` invalid request, `503` when `DATABASE_URL` is unset, `500` generic failure. Success logs emit `retrieval_debug_completed` with safe metadata only, including branch result counts but not query text or chunk content.

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/retrieval-debug \
  -H 'Content-Type: application/json' \
  -d '{"query":"JWT refresh token rotation for OAuth2 REST API","strategies":["vector"],"vector":{"top_k":20,"threshold":0.6},"max_results":10}' \
  | python3 -m json.tool

curl -sS -X POST http://127.0.0.1:8000/api/v1/retrieval-debug \
  -H 'Content-Type: application/json' \
  -d '{"query":"JWT refresh token rotation for OAuth2 REST API","strategies":["lexical"],"lexical":{"top_k":20},"max_results":10}' \
  | python3 -m json.tool

curl -sS -X POST http://127.0.0.1:8000/api/v1/retrieval-debug \
  -H 'Content-Type: application/json' \
  -d '{"query":"JWT refresh token rotation for OAuth2 REST API","strategies":["vector","lexical","hybrid"],"vector":{"top_k":20},"lexical":{"top_k":20},"hybrid":{"method":"rrf","rrf_k":60},"max_results":10}' \
  | python3 -m json.tool

curl -sS -X POST http://127.0.0.1:8000/api/v1/retrieval-debug \
  -H 'Content-Type: application/json' \
  -d '{"query":"JWT refresh token rotation","strategies":["vector","lexical","hybrid"],"filters":{"client_sector":"finance","main_technology":"python","tags":["backend"],"year":{"from":2023,"to":2025}},"max_results":10}' \
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
  -d '{"query":"REST API with OAuth authentication for fintech sector","strategies":["vector","lexical"],"vector":{"top_k":10},"lexical":{"top_k":10},"max_results":5}' \
  | python3 -m json.tool

curl -sS -X POST http://127.0.0.1:8000/api/v1/retrieval-debug \
  -H 'Content-Type: application/json' \
  -d '{"query":"REST API with OAuth authentication","strategies":["vector","lexical","hybrid"],"filters":{"document_type":"historical_budget","client_sector":"finance","tags":["backend"],"year":{"from":2023}},"max_results":5}' \
  | python3 -m json.tool

curl -sS "http://127.0.0.1:8000/api/v1/retrieval-debug/chunks/156?query=OAuth%20backend" \
  | python3 -m json.tool

uv run pytest tests/embedding_pipeline/test_retrieval_debug_*.py -q
```

Use this internal API to compare semantic and lexical retrieval: vector `distance` remains raw cosine distance, vector `score` is normalized similarity, lexical `score` is branch-local min-max normalized `ts_rank_cd`, and `matched_terms` shows the exact full-text evidence for technical tokens such as acronyms, versions, and identifiers. Add `filters` when you need a controlled corpus slice; filters are applied to vector and lexical candidates before hybrid fusion, so diffs explain retrieval behavior only inside the selected subset.

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

**(e) Retrieval debug metadata filters**

`POST /api/v1/retrieval-debug` can scope vector, lexical, and hybrid candidate sets through `filters`. Scalar fields (`client_sector`, `main_technology`, `source_name`, `language`) use JSONB containment against `chunks.metadata`, `tags` requires all requested tags to be present, and `year` uses inclusive numeric bounds. `document_type` is document-level and joins `documents`. This keeps `/api/v1/search` unchanged while letting operators isolate relevance variables inside the internal debug API.

**(f) Indexed lexical full-text search**

The lexical branch now uses migration `0003_add_chunks_content_tsv_and_trgm.py`: `chunks.content_tsv` is a stored generated `tsvector`, `ix_chunks_content_tsv_gin` indexes full-text matching, and `pg_trgm` plus `ix_chunks_content_trgm` support exact technical-token diagnostics. The debug API response shape is unchanged; verify planner behavior with `EXPLAIN` after `uv run alembic upgrade head` (see [docs/technical/README.md §25](docs/technical/README.md#25-indexed-lexical-search-feature-048)).

### Out of scope

Faceting, filter suggestions, ranking benchmarks, and retrieval tuning are **not** implemented here.

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
| `401` on `/api/v1/retrieval` or `/api/v1/estimate/rag` | API key required but missing or wrong | Set `RETRIEVAL_API_KEY` / `ESTIMATE_API_KEY` in `.env` and send matching `X-API-Key`; leave keys empty for open local dev |
| `429` on retrieval or RAG | Rate limit exceeded | `RATE_LIMIT_ENABLED=true` — wait for `Retry-After` (60s) or reduce request rate |

More detail: [docs/technical/README.md §20](docs/technical/README.md#20-troubleshooting).

---

## Security

- **Never commit `.env`** — it is gitignored; `.env.example` holds placeholders only.
- API keys are read from environment variables via `pydantic-settings`.
- Logs must not include credentials, tokens, or full user transcripts.
- The default test suite does not require real provider keys.
- Session state is **in-memory only** — not suitable for multi-instance production without external storage.
- Guardrails reduce risk but are not a substitute for production content moderation or auth.

### API hardening (retrieval & RAG)

Optional protection for **`POST /api/v1/retrieval`** and **`POST /api/v1/estimate/rag`** only. CAG v1/v2, sessions, embeddings ingest, and search remain open by default.

| Variable | Default | Behavior |
|----------|---------|----------|
| `RETRIEVAL_API_KEY` | *(empty)* | When non-empty, retrieval requests must send `X-API-Key` with a constant-time match |
| `ESTIMATE_API_KEY` | *(empty)* | Independent key for RAG estimate; retrieval key does not unlock RAG |
| `RATE_LIMIT_ENABLED` | `false` | When `true`: retrieval **120/minute**, RAG estimate **10/minute** per API-key bucket (client IP when no header) |

**Request correlation:** every response includes `X-Request-ID`. Send your own id to trace logs across services; otherwise the API generates one.

**Staging / production example** (`.env`):

```text
RETRIEVAL_API_KEY=change-me-retrieval
ESTIMATE_API_KEY=change-me-estimate
RATE_LIMIT_ENABLED=true
```

```bash
# Retrieval (401 without header when RETRIEVAL_API_KEY is set)
curl -sS -X POST http://127.0.0.1:8000/api/v1/retrieval \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: change-me-retrieval' \
  -H 'X-Request-ID: my-trace-001' \
  -d '{"query":"API REST con OAuth2","mode":"B"}'

# RAG estimate (401 without header when ESTIMATE_API_KEY is set)
curl -sS -X POST http://127.0.0.1:8000/api/v1/estimate/rag \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: change-me-estimate' \
  -d '{"question":"Plataforma e-commerce con Stripe y OAuth2"}'

# Rate limit breach → 429 with Retry-After: 60 and JSON detail
```

Automated coverage: `tests/test_api_security.py`, `tests/test_api_rate_limiting.py`, `tests/test_request_id_middleware.py`.

### Runtime config (Redis overrides)

`GET`/`PUT /api/v1/config/retrieval` and `GET`/`PUT /api/v1/config/models` let operators toggle a few settings without restarting the app. Each `PUT` stores a small JSON blob in Redis (key `master-ia:runtime:retrieval` or `master-ia:runtime:models`); each `GET` merges that override over env `Settings` (Redis wins for the fields it sets, env fills the rest). These routes are **open in dev** (no `X-API-Key`) — see [feature-057](docs/work-items/feature-057-runtime-config-redis-endpoints.md).

| Variable | Default | Behavior |
|----------|---------|----------|
| `REDIS_URL` | *(empty)* | When set, config overrides persist in Redis; when empty, `GET` returns env defaults and `PUT` returns `503` |

`POST /api/v1/retrieval` honors the `rerank_enabled` override immediately on the next request (no restart) — modes `C`/`D` degrade to `A`/`B` with a `warnings` entry when disabled, same as the `RETRIEVAL_RERANK_ENABLED` env kill switch.

```bash
# Effective retrieval config (Redis override merged over Settings)
curl -sS http://127.0.0.1:8000/api/v1/config/retrieval

# Disable rerank at runtime (no restart needed)
curl -sS -X PUT http://127.0.0.1:8000/api/v1/config/retrieval \
  -H 'Content-Type: application/json' \
  -d '{"rerank_enabled": false}'

# Effective model config
curl -sS http://127.0.0.1:8000/api/v1/config/models

# Override the structured-output model
curl -sS -X PUT http://127.0.0.1:8000/api/v1/config/models \
  -H 'Content-Type: application/json' \
  -d '{"structured_model": "gpt-4.1-mini"}'
```

Automated coverage: `tests/test_runtime_config.py`, `tests/test_runtime_config_api.py`, `tests/test_runtime_config_retrieval_integration.py`.

---

**Status:** Active development · **Version:** `0.1.0` (see `pyproject.toml`)
