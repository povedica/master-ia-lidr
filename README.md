# Estimador CAG

A FastAPI service that converts **structured project context** into a software estimate using **Context-Augmented Generation (CAG)**. Few-shot reference examples are injected per estimation mode into the system prompt; the composed project brief is sent as the user message to the configured LLM provider.

---

## Table of contents

1. [Requirements](#requirements)
2. [Setup](#setup)
3. [Running the application](#running-the-application)
   - [Docker (recommended)](#docker-recommended)
   - [Local development](#local-development)
4. [Web UI](#web-ui)
5. [API reference](#api-reference)
6. [Configuration](#configuration)
7. [Tests](#tests)

---

## Requirements

| Path | Requirements |
|------|-------------|
| Docker (full stack) | [Docker](https://docs.docker.com/get-docker/) with Compose v2 — no Python or Node needed on the host |
| Local development | Python 3.11+, [uv](https://docs.astral.sh/uv/), Node.js 20+ with npm (for `web/`) |

---

## Setup

1. Copy the environment template and fill in your credentials:

```bash
cp .env.example .env
# Set OPENAI_API_KEY (and any other provider keys) in .env — never commit .env.
```

2. At least one LLM provider key is required (`OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY`). See [Configuration](#configuration) for all available variables.

---

## Running the application

### Docker (recommended)

Runs the API and the web UI in containers without installing Python or Node locally.

**Production mode:**

```bash
docker compose up --build
```

If you only start `app` (or omit services), Redis may not run; either use `docker compose up` as above or start Redis explicitly: `docker compose up -d redis`. With the default compose file, `app` is configured to **depend on** `redis` so a normal `up` brings both up.

| Service | URL |
|---------|-----|
| FastAPI API | `http://127.0.0.1:8000` |
| OpenAPI docs | `http://127.0.0.1:8000/docs` |
| Web UI (nginx) | `http://127.0.0.1:5175` |
| Redis Stack (semantic cache / RediSearch vectors) | `redis://127.0.0.1:6379` |
| Redis Insight (web UI for Redis) | `http://127.0.0.1:5540` — add database: host `redis`, port `6379` (Compose service name) |

Set `SEMANTIC_CACHE_REDIS_URL` in `.env` when exercising the semantic cache: use `redis://redis:6379/0` for the `app` container, or `redis://127.0.0.1:6379/0` if the API runs on the host while Redis runs in Compose.

**Development mode** (API live-reload via Uvicorn `--reload`, bind-mounted source):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

The dev override bind-mounts the repo into the container and restarts the API on code changes. The `web` service remains the same static nginx container.

Quick health check:

```bash
curl -s http://127.0.0.1:8000/health
```

To build the web image with a custom API URL:

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

---

## Web UI

The `web/` package is a **React + Vite + TypeScript** browser UI. On load it creates a session (`POST /api/v1/sessions`), then submits the simplified form to `POST /api/v1/sessions/{session_id}/estimate` and shows **project metadata** and the structured **estimate** in separate panels. See `web/README.md` for dev commands.

- **Docker:** the `web` image builds assets at container build time and serves them with nginx. No Node needed on the host.
- **Production build smoke check:**

```bash
cd web
npm run build
npm run preview
```

For the v1 Markdown + SSE contract (optional), see [docs/technical/README.md](docs/technical/README.md).

---

## API reference

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/` | Root — links to docs and routes |
| `POST` | `/api/v1/estimate` | Synchronous estimation |
| `POST` | `/api/v1/estimate/stream` | Markdown estimation with SSE (`chunk` / `done` / `error`) |
| `POST` | `/api/v2/estimate` | Structured synchronous estimation |
| `POST` | `/api/v1/sessions` | Create an in-memory session (`201` + `session_id`) |
| `POST` | `/api/v1/sessions/{session_id}/estimate` | Simplified transcript-centered submit (structured envelope) |

Full schema available at `http://127.0.0.1:8000/docs`.

### Simplified session estimation

Create a session, then submit a transcript-centered estimate on `POST /api/v1/sessions/{session_id}/estimate`. The API returns `project_metadata`, `warnings`, `input_payload`, and a structured `estimate` (same core shape as `POST /api/v2/estimate`).

**Transports**

| Content-Type | Use case |
|--------------|----------|
| `application/json` | SPA / API clients; optional inline `AttachmentRef.content_base64` |
| `multipart/form-data` | Direct file upload; repeat form field `attachments` per file |

Transcript minimum length is **80** characters after trim. On follow-up submits, `project_name`, `project_type`, and `target_audience` may be omitted when the session already has derived metadata.

**Attachment strategy (Path B)**

Files are read in-process and converted to text locally (`DocumentTextExtractor` for `text/plain`, `text/markdown`, `application/pdf`). We use Path B because:

- No external file store or provider Files API keys are required for the exercise or default CI.
- Integration tests stay deterministic with in-memory sessions and fakes.
- The same MIME and size limits apply to JSON base64 and multipart uploads.

Path A (OpenAI/Anthropic Files API with pre-registered `file_id`) is deferred until product needs provider-native file handles.

**Metadata and memory**

- Each submit runs heuristic `derive_project_metadata()` from form fields, transcript, and extracted attachment text.
- `merge_derived_metadata()` combines the new snapshot with `session.last_derived_metadata` (constraints union, latest attachment summary, deduped warnings).
- The structured LLM call receives a bounded `conversation_history` (compact user/assistant pairs) plus the full current user prompt (including attachment context), not only the latest system prompt.

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/sessions | jq

# JSON submit
curl -s -X POST http://127.0.0.1:8000/api/v1/sessions/<session_id>/estimate \
  -H "Content-Type: application/json" \
  -d '{
    "project_name": "Partner portal",
    "project_type": "web_saas",
    "transcript": "Discovery notes: B2B partners need ticket intake, SSO, dashboards, CSV export. Timeline flexible.",
    "target_audience": "b2b_smb",
    "attachments": []
  }' | jq

# Multipart submit (one file)
curl -s -X POST http://127.0.0.1:8000/api/v1/sessions/<session_id>/estimate \
  -F "project_name=Partner portal" \
  -F "project_type=web_saas" \
  -F "target_audience=b2b_smb" \
  -F "transcript=Discovery notes: B2B partners need ticket intake, SSO, dashboards, CSV export. Timeline flexible." \
  -F "attachments=@./brief.txt;type=text/plain" | jq
```

Stateless `POST /api/v1/estimate` and `POST /api/v2/estimate` are unchanged.

### Example request

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/estimate \
  -H "Content-Type: application/json" \
  -d '{
    "project_summary": "B2B portal for partners to submit requests and track SLA status.",
    "project_type": "web_saas",
    "target_audience": "b2b_smb",
    "project_description": "Responsive web app for authenticated partners to submit structured tickets, follow approval workflows, and view status dashboards.",
    "deliverables": [
      "Partner authentication with SSO and role-based access control",
      "Configurable ticket intake forms and commenting threads",
      "Operations dashboards with CSV export and saved filters"
    ],
    "delivery_urgency": "standard",
    "data_sensitivity": "internal_business",
    "detail_level": "medium",
    "output_format": "phases_table"
  }'
```

See `app/schemas/estimation_request.py` for the full request shape.

### Notable request fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `evaluate` | `bool` | `true` | Include structural score and output validation in the response |
| `preprocessing` | `none` \| `inline_cleaning` \| `two_phase` | `none` | Pre-processing strategy before the main estimate |

### Response fields

| Field | When present | Description |
|-------|-------------|-------------|
| `estimation` | Always | The estimate text |
| `score` | When `evaluate=true` | Structural quality score in `[0, 1]` |
| `structure_evaluation` | When `evaluate=true` | Section-level structural checks |
| `output_validation` | When `evaluate=true` | Mode-specific section checks |
| `degraded` | When static fallback used | `true` if the response is not from a live model |
| `mode`, `model`, `provider`, `request_id`, `timestamp`, `latency_ms`, `prompt_version`, `examples_version`, `usage` | `DEV_MODE=true` only | Operational and debugging metadata |

### Estimation modes

The service routes each request to one of four depth modes based on decision context:

| Mode | Primary use |
|------|------------|
| `basic` | Quick sizing, early discovery |
| `standard` | Internal planning (default) |
| `professional` | Presales and client-facing proposals |
| `expert_review` | High-stakes validation and risk surfacing |

Mode-specific system instructions live in `app/context/prompts/` (`basic.txt`, `standard.txt`, `professional.txt`, `expert_review.txt`). Edit those files to tune wording without changing Python code.

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

Disable with `LLM_DOMAIN_GUARDRAIL_ENABLED=false` (see [Configuration](#configuration)).

### Structured API (v2) guardrails

`POST /api/v2/estimate` runs the guarded pipeline: deterministic input checks (prompt injection, basic PII, domain relevance, optional moderation placeholder), a structured LLM call, then lightweight output semantic checks (confidence floor, leakage heuristics). Domain mismatches return HTTP `200` with `final_status="degraded"`, `reason_code`, `audit_id`, and `safe_to_cache=false` instead of a silent success. Enforced unsafe-input policies still return HTTP `422` with the same stable `code` / `audit_id` shape. Rollout overrides per guardrail use the `GUARDRAIL_ROLLOUT_*` keys documented in `.env.example`.

---

## Configuration

Copy `.env.example` for the full list of available variables. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Required for OpenAI provider |
| `ANTHROPIC_API_KEY` | — | Required for Anthropic provider |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model id |
| `ANTHROPIC_MODEL` | — | Anthropic model id |
| `DEFAULT_LLM_MODEL` | `openai/gpt-4o-mini` | LiteLLM-style canonical model reference |
| `LLM_PROVIDERS` | `openai,anthropic` | Ordered fallback chain |
| `LLM_AUTH_FALLBACK` | `false` | Treat auth failures as fallback instead of `503` |
| `STATIC_FALLBACK_ENABLED` | `false` | Append deterministic local fallback when all providers fail |
| `LLM_DOMAIN_GUARDRAIL_ENABLED` | `true` | Reject out-of-domain requests before provider calls |
| `FORCED_ESTIMATION_MODE` | — | Override adaptive routing (`basic`, `standard`, `professional`, `expert_review`) |
| `DEV_MODE` | `false` | Include provider, routing, timing, versions, and usage in the response |
| `ESTIMATION_OUTPUT_PERSIST_ENABLED` | `false` | Save successful estimate outputs to `output-responses/` |
| `ESTIMATION_STATS_LOG_ENABLED` | `false` | Append NDJSON usage metadata to `output-stats/estimation-stats.jsonl` |
| `FRONTEND_ORIGINS` | *(local defaults)* | Comma-separated allowed CORS origins |
| `GUARDRAIL_RULES_VERSION` | *(empty)* | Optional label stored with pipeline metadata |
| `ESTIMATION_MIN_OUTPUT_CONFIDENCE` | `0.05` | Minimum structured-result confidence before v2 output downgrade |
| `GUARDRAIL_ROLLOUT_*` | *(empty)* | Optional per-guardrail rollout override (`disabled`, `log_only`, `enforce`) |
| `SEMANTIC_CACHE_*` | see `.env.example` | Optional semantic cache for `POST /api/v2/estimate` (defaults: off / log-only; Redis Stack adapter when URL is set) |

Chat completions go through **[LiteLLM](https://github.com/BerriAI/litellm)**. Use short model ids in `OPENAI_MODEL` / `ANTHROPIC_MODEL` (the `openai/` and `anthropic/` prefixes are added automatically), or set a fully qualified LiteLLM id in `DEFAULT_LLM_MODEL`.

---

## Tests

Run the full test suite (no real API calls — all provider clients are mocked):

```bash
uv run pytest
```

### Integration tests (sessions)

Session memory, metadata re-injection, attachments, and sliding-window history are covered by an in-process integration suite that uses the real FastAPI app and `SimplifiedSessionEstimationService`, with `complete_structured` faked (no network):

```bash
uv run pytest tests/test_sessions_integration.py
```

Optional environment variables (also in `.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `SESSION_INTEGRATION_TEST_LLM_MODEL` | _(empty → `OPENAI_MODEL`)_ | OpenAI model id passed into the integration harness (`openai_model` / LiteLLM route). Recorded on fake calls as `litellm_model`. |
| `SESSION_INTEGRATION_TEST_USE_REAL_LLM` | `false` | When `true`, disables the fake and calls the real structured LLM (`OPENAI_API_KEY` required). Deterministic fake-based tests are skipped; only `test_estimate_submit_live_llm_smoke` runs. |

Example — keep the fake but pin the model id the stack would use:

```bash
SESSION_INTEGRATION_TEST_LLM_MODEL=gpt-4o uv run pytest tests/test_sessions_integration.py -v
```

Example — live smoke against OpenAI (costs tokens; not for CI):

```bash
SESSION_INTEGRATION_TEST_USE_REAL_LLM=true \
SESSION_INTEGRATION_TEST_LLM_MODEL=gpt-4o-mini \
OPENAI_API_KEY=sk-... \
uv run pytest tests/test_sessions_integration.py::test_estimate_submit_live_llm_smoke -v
```

- **Attachments:** Path B — local text extraction (`text/plain`, `text/markdown`, `application/pdf`) via `DocumentTextExtractor`; JSON base64 or multipart `attachments` parts; integration tests build a minimal **PDF** in-process (`tests/fixtures/attachment_bytes.py`).
- **Metadata:** heuristic `derive_project_metadata()` per submit plus `merge_derived_metadata()` across turns; not the LLM metadata extractor on this path.
- **Memory:** bounded `conversation_history` is passed to `complete_structured` together with the current user prompt. See [Simplified session estimation](#simplified-session-estimation).

Run with verbose output:

```bash
uv run pytest -v
```

Run in a Docker dev container:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm app uv run pytest
```
