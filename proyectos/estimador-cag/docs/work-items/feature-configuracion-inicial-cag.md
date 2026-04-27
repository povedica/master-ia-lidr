# Feature: Configuración Inicial del Estimador CAG

## Objective

Create the initial Python project structure for `estimador-cag`, configured with `uv`, FastAPI, environment-based settings, and a first LLM-backed estimation endpoint using Context-Augmented Generation.

The goal is to build a minimal but well-organized learning project where HTTP routing, business logic, static context, configuration, and provider integration are separated from the beginning. This structure is intentionally simple, but it avoids putting all logic in a single file and prepares the project to evolve safely.

## Context

This project belongs to session 02 of the AI Engineering master work. It will be created under:

```text
proyectos/estimador-cag/
```

The project will use:

- Python 3.11+
- `uv` for dependency and environment management
- FastAPI as the initial web framework
- `pydantic-settings` for typed configuration
- OpenAI as the initial LLM provider
- `gpt-4o-mini` as the default low-cost model
- `.env` for local secrets and `.env.example` for documented variables

Cursor only loads project configuration from **the workspace root**. The shared rules and commands for this repo (incluidas las de Python, FastAPI y AI Engineering del estimador) viven en:

```text
.cursor/rules/
.cursor/commands/
```

## Scope

### Includes

- Create the project directory and initialize it with `uv`.
- Create the initial application structure:

```text
estimador-cag/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── routers/
│   │   ├── __init__.py
│   │   └── estimations.py
│   ├── services/
│   │   ├── __init__.py
│   │   └── llm_service.py
│   └── context/
│       ├── __init__.py
│       └── examples.py
├── .env
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

- Add required dependencies:
  - `fastapi`
  - `uvicorn[standard]`
  - `pydantic-settings`
  - `openai`
  - `python-dotenv`
- Implement configuration with Pydantic `BaseSettings`.
- Add static few-shot estimation examples in `app/context/examples.py`.
- Implement an LLM service that builds a system prompt with examples and sends the user transcription.
- Implement `POST /api/v1/estimate`.
- Implement `GET /health`.
- Document runtime commands with `uv`.

### Excludes

- No database persistence for estimates yet.
- No authentication or user management.
- No frontend.
- No production deployment.
- No real cost tracking unless added later.
- No Anthropic integration in the first pass unless explicitly selected.
- No automated CI/CD in the first pass.

## Functional Requirements

### FR-1: Project Setup with `uv`

The project must be initialized so dependencies and execution use `uv`.

Expected setup commands:

```bash
uv init
uv add fastapi "uvicorn[standard]" pydantic-settings openai python-dotenv
```

The project must be runnable with:

```bash
uv run uvicorn app.main:app --reload
```

### FR-2: Environment Configuration

`app/config.py` must load configuration from environment variables using Pydantic `BaseSettings`.

Required variables:

```text
LLM_PROVIDER=openai
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_TIMEOUT_SECONDS=30
APP_ENV=local
DEV_MODE=false
LOG_LEVEL=INFO
```

Optional future variables:

```text
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=
```

Rules:

- `.env` contains local real values and must not be committed.
- `.env.example` documents the variables without real secrets.
- `.gitignore` must include `.env`.
- Code must never hardcode API keys.

### FR-3: Static Context Examples

`app/context/examples.py` must define at least two previous estimation examples.

Each example must include:

- `meeting_summary`: summary of the original client meeting.
- `estimation`: generated estimate with tasks, hours, cost or delivery notes.

These examples are the static context used by the CAG approach. They act as few-shot examples for the model.

### FR-4: LLM Service

`app/services/llm_service.py` must expose a function or service that:

1. Builds the system prompt.
2. Injects the static estimation examples.
3. Sends the new meeting transcription as the user message.
4. Calls OpenAI using the configured model.
5. Returns the generated estimation.

Message pattern:

```text
[system]   -> Instructions + previous estimation examples
[user]     -> Meeting transcription to estimate
[assistant] -> Model-generated estimation
```

The service must be the only place where the OpenAI SDK is used in the first version.

### FR-5: Estimation Endpoint

`app/routers/estimations.py` must expose:

```text
POST /api/v1/estimate
```

Request body:

```json
{
  "transcription": "En la reunión con el cliente se discutió la necesidad de..."
}
```

Response body:

```json
{
  "estimation": "## Estimación: ...",
  "model": "gpt-4o-mini",
  "provider": "openai",
  "request_id": "est_9f7c5a7e5d4b",
  "timestamp": "2026-04-27T09:50:13Z",
  "latency_ms": 1820,
  "prompt_version": "v1",
  "examples_version": "static-v1",
  "usage": {
    "prompt_tokens": 920,
    "completion_tokens": 410,
    "total_tokens": 1330,
    "estimated_cost_usd": 0.000384
  }
}
```

`usage` is included only when `DEV_MODE=true`; `estimated_cost_usd` lives inside `usage`.

Response metadata meaning:

- `request_id`: unique request identifier generated by the API for traceability.
- `timestamp`: UTC response generation time.
- `latency_ms`: end-to-end processing time measured by the route handler.
- `prompt_version`: explicit version of the prompt template used in this run.
- `examples_version`: explicit version of static context examples injected in this run.
- `usage`: token accounting from provider (`prompt_tokens`, `completion_tokens`, `total_tokens`) plus `estimated_cost_usd`, only in dev mode.

Why `prompt_version` and `examples_version` matter:

- They make output reproducible and auditable.
- They allow quality regression analysis across sessions.
- They separate "model/provider effect" from "prompt/context effect".
- They simplify A/B comparisons when prompt or examples evolve.

Versioning policy for this feature:

- Bump `prompt_version` whenever instructions, constraints, or output format change.
- Bump `examples_version` whenever `app/context/examples.py` changes in meaning.
- Keep versions explicit in API responses so downstream consumers can log them.

`DEV_MODE` behavior:

- `DEV_MODE=false` (default): hide internal token/cost telemetry from response.
- `DEV_MODE=true`: include `usage` (including `estimated_cost_usd`) for local debugging, tuning, and cost awareness.

This keeps production payloads stable/minimal while preserving deep observability in development.

Request and response schemas must be defined with Pydantic.

### FR-6: FastAPI Application

`app/main.py` must:

- Create the FastAPI app.
- Configure title and description.
- Include the estimations router with prefix `/api/v1`.
- Expose `GET /health`.
- Keep Swagger available at `/docs`.

### FR-7: Verification

The basic manual verification command is:

```bash
uv run uvicorn app.main:app --reload
```

Health check:

```bash
curl http://localhost:8000/health
```

Estimation check:

```bash
curl -X POST http://localhost:8000/api/v1/estimate \
  -H "Content-Type: application/json" \
  -d '{
    "transcription": "En la reunión con el equipo de marketing, el cliente explicó que necesita una landing page con formulario de contacto, integración con su CRM actual (HubSpot), y una sección de blog con editor WYSIWYG. El plazo ideal sería tenerlo listo en 4 semanas. El diseño ya existe en Figma."
  }'
```

## Technical Approach

### Architecture

Use a deliberately small layered structure:

- `routers/`: HTTP boundary and request/response schemas.
- `services/`: business logic and LLM provider call.
- `context/`: static examples injected into the prompt.
- `config.py`: environment-based typed settings.
- `main.py`: FastAPI composition root.

### Provider Boundary

OpenAI must be isolated in `llm_service.py`. If Anthropic is added later, introduce provider selection through `LLM_PROVIDER` without changing router code.

### Prompting

The system prompt should:

- Define the model as an expert software estimator.
- Explain that previous examples are reference patterns.
- Ask for a structured estimate.
- Encourage clear assumptions and task breakdown.

### Error Handling and Logging

The first implementation should handle:

- missing API key
- provider timeout
- rate limit
- invalid or empty response
- unexpected provider errors

Logs must not include API keys or sensitive transcriptions unless intentionally sanitized.

## Acceptance Criteria

### Functional

- [x] `uv run uvicorn app.main:app --reload` starts the API without errors (from `proyectos/estimador-cag/`).
- [x] `GET /health` returns status 200.
- [x] `POST /api/v1/estimate` accepts a `transcription` field.
- [x] `POST /api/v1/estimate` returns `estimation`, `model`, `provider`, and technical metadata (`request_id`, `timestamp`, `latency_ms`, prompt/context version, usage when available).
- [x] The generated estimation is influenced by the static examples (injected in the system prompt; verify output with a real key when desired).
- [x] Swagger is available at `/docs`.

### Technical

- [x] API keys are loaded from `.env` and never hardcoded.
- [x] `.env.example` documents required variables without real secrets.
- [x] `.env` is listed in `.gitignore`.
- [x] OpenAI SDK usage is isolated in the service layer.
- [x] Route handlers do not contain provider-specific logic.
- [x] Static examples live in `app/context/examples.py`.

### Testing

- [x] Prompt/context construction can be tested without real OpenAI calls.
- [x] LLM provider calls can be mocked.
- [x] Settings loading can be tested with controlled environment variables.
- [x] Endpoint behavior can be tested without real API keys once tests are introduced.

## Test Plan

### Unit Tests

- Test settings parsing with environment overrides.
- Test prompt construction includes both examples.
- Test the service handles empty transcriptions.
- Test provider errors are converted into safe application errors.

### API Tests

- Test `GET /health`.
- Test `POST /api/v1/estimate` validates missing `transcription`.
- Test `POST /api/v1/estimate` returns the expected response shape using a mocked LLM service.

### Manual Checks

- Run the API with `uv run uvicorn app.main:app --reload`.
- Check `/docs` in the browser.
- Call `/api/v1/estimate` with `curl`.
- Confirm no secrets appear in code, logs, or docs.

## Implementation Plan

### Step 1: Project Scaffold

Create the project folder, initialize `uv`, add dependencies, and create the base `app/` package.

### Step 2: Settings and Secrets

Create `config.py`, `.env.example`, `.gitignore`, and local `.env`.

Do not commit `.env`.

### Step 3: Static Context

Add two realistic estimation examples in `app/context/examples.py`.

### Step 4: LLM Service

Build the prompt, inject examples, call OpenAI, and return model output.

### Step 5: API Router

Create request/response schemas and implement `POST /api/v1/estimate`.

### Step 6: FastAPI App

Register router, add `/health`, and configure API metadata.

### Step 7: Verification

Run the server, call health, call estimate endpoint, and check Swagger.

## Documentation Plan

- Update project `README.md` with setup, `.env.example`, and runtime commands.
- Record implementation progress in `second-brain-master-ia/proyectos/estimador-cag/sesiones/sesion-02-estimador-cag.md`.
- Promote reusable learnings about CAG, few-shot context, or provider boundaries to `aprendizajes/` if they become useful beyond this feature.

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
| `b8e737c` | `docs(cursor): add estimador-cag project rules and commands` | Adds Python/FastAPI/AI Cursor rules and commands; first under `proyectos/estimador-cag/.cursor/` (see following `refactor(cursor)` commit). |
| `d1f3c57` | `docs(cursor): align commit-pending with feature commit reporting` | Commit log favors the feature doc; if unclear, ask and suggest destination before `git commit`. |
| `9c8c325` | `refactor(cursor): colocate project rules and commands at repo root` | Moves estimator rules/commands to repo-root `.cursor/` so Cursor loads them. |
| `0320098` | `docs(cursor): English commit workflow and cursor standards` | Translates `commit-pending` to English; English commit-log column; expands `start-task` and language rule in `00-base-standards`. |
| `d8a5a8e` | `feat(estimador-cag): add CAG estimator FastAPI subproject` | Adds `proyectos/estimador-cag` with FastAPI, pydantic-settings, static few-shot examples, isolated OpenAI service, `POST /api/v1/estimate`, `GET /health`, pytest suite (no live API calls), and `uv.lock`. |
| `3e6e4b6` | `feat(estimador-cag): add root URL with API pointers` | Adds `GET /` JSON index for browser visits; README note on optional `/favicon.ico` 404; test coverage. |
| `b17ad30` | `feat(estimador-cag): add DEV_MODE-gated usage telemetry and cost estimate` | Extends `/api/v1/estimate` metadata, gates `usage` in `DEV_MODE`, adds token-based `estimated_cost_usd` inside `usage`, and updates tests/docs. |
| `ad7084a` | `feat(cursor): add lightweight workflow commands, skills, and subagents` | Adds DSM-inspired Cursor workflow pieces adapted to `master-ia`: requirement commands, validation rules, reusable skills, and lightweight technical subagents. |

## Notes

This feature intentionally does not implement persistence, authentication, or frontend concerns. The objective is to get a clean and testable AI Engineering baseline before adding complexity.
