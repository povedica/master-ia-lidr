# Estimador CAG

FastAPI service that turns a meeting transcription into a structured software estimate using **Context-Augmented Generation (CAG)**: few-shot reference text is loaded per estimation mode from `app/context/examples/<basic|standard|professional|expert_review>/*.txt`, sampled in Python via `app/context/examples.py` (a random subset of 2–4 examples per request; modes without samples yet fall back to `standard`), and injected into the system prompt; the live meeting text is sent as the user message.

## Documentation mirror

Project notes (sessions, work items, learnings, retrospectives) are authored in **Obsidian** under `second-brain-master-ia/proyectos/estimador-cag/` (see repo root `README.md` for the symlink). A **read-only replica** of that folder is kept in git at `docs/` so clones have the latest exported documentation without the vault.

For deeper technical documentation, see `docs/technical/README.md`. All prose under `docs/technical/` is **English** only.

From the **repository root**:

```bash
bash scripts/sync-estimador-cag-docs.sh
```

Requirements: valid `second-brain-master-ia` symlink and `rsync` on your machine. The script uses `rsync --delete`: files removed in the vault are removed from `docs/`. Never put real API keys or secrets in vault notes that will be mirrored here.

## Requirements

- Python 3.11
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
cd proyectos/estimador-cag
uv sync --group dev
cp .env.example .env
# Set OPENAI_API_KEY in .env (never commit .env).
```

Chat completions go through **[LiteLLM](https://github.com/BerriAI/litellm)** in `app/services/ai_model_service.py`. Use `OPENAI_MODEL` / `ANTHROPIC_MODEL` with short ids (defaults add the `openai/` and `anthropic/` prefixes automatically) or paste a fully qualified LiteLLM id that already contains `provider/model`. `.env.example` also documents **`DEFAULT_LLM_MODEL`** (`openai/gpt-4o-mini` default) as the canonical LiteLLM-style reference for operators; **`GEMINI_API_KEY`** is optional for future `gemini/...` routes.

Configuration reads **`proyectos/estimador-cag/.env` by absolute path** (next to the `app/` package), so variables such as `FORCED_ESTIMATION_MODE` still apply when you start Uvicorn from another working directory (for example the monorepo root).

## Run the API

```bash
cd proyectos/estimador-cag
uv run uvicorn app.main:app --reload
```

- Root: `GET http://127.0.0.1:8000/` (JSON pointers to docs and routes)
- Health: `GET http://127.0.0.1:8000/health`
- OpenAPI: `http://127.0.0.1:8000/docs`

Browsers may request `/favicon.ico`; there is no favicon asset, so that request may return 404 and can be ignored.

## Streamlit demo UI (manual testing)

Internal browser UI only; it delegates to **`EstimationService`** (same as `POST /api/v1/estimate`). Configure keys and models via `.env` as for the API (see [.env.example](.env.example)).

```bash
cd proyectos/estimador-cag
uv sync
uv run streamlit run app/streamlit_app.py
```

The app validates empty input locally. Domain guardrail, configuration, and provider failures show short messages intended for testers—no stack traces in the UI.

## Docker

Reproducible runtime for **this** subproject only. The `Dockerfile` and `docker-compose.yml` at the **monorepo root** build a different demo app (`app/` at the root), not `estimador-cag`.

From `proyectos/estimador-cag`:

```bash
cd proyectos/estimador-cag
cp .env.example .env
# Edit .env (API keys, etc.); never commit .env.
docker compose up --build
```

- Service listens on `http://127.0.0.1:8000` (same routes as local `uv run`).

Development compose (bind-mounts the project, runs `uv sync --frozen --group dev` on start, Uvicorn with `--reload`):

```bash
cd proyectos/estimador-cag
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Quick check after `up`:

```bash
curl -s http://127.0.0.1:8000/health
```

Optional: run tests in a one-off container (uses the dev override so the project — including `tests/` — is bind-mounted and dev dependencies are synced on start):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm app uv run pytest
```

## Example request

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/estimate \
  -H "Content-Type: application/json" \
  -d '{"transcription":"The client needs a REST API for orders with idempotent POST."}'
```

Optional JSON body fields (same `POST`):

- **`evaluate`** (`bool`, default `true`, same as `ai-engineering/estimator`): when `true`, runs `evaluate_estimation_structure` in the router and returns `score`, `structure_evaluation`, and `output_validation` (mode-specific section checks). Set `false` to omit those fields. See [docs/technical/output-validation-and-input-score.md](docs/technical/output-validation-and-input-score.md).
- **`preprocessing`** (`none` | `inline_cleaning` | `two_phase`, default `none`): `inline_cleaning` adds meeting-cleaning instructions to the system prompt; `two_phase` runs an extraction LLM call before the main estimate and merges phase-one tokens into `usage.preprocessing_*` (requires a live provider before static fallback).

Response fields:

- **Always:** `estimation` (the markdown estimate).
- **When `evaluate` is true (default):** **`score`** and **`structure_evaluation`** (Level-1 structural metric, same formula as `ai-engineering/estimator`) plus **`output_validation`** (mode-specific section checks).
- **When static fallback is used and `DEV_MODE=false`:** `degraded` is also present (`true`) so clients can tell the response is not from a live model.
- **When `DEV_MODE=true`:** `mode`, `model`, `provider`, `request_id`, `timestamp`, `latency_ms`, `prompt_version`, `examples_version`, `finish_reason`, optional `assessment`, optional `mode_eligibility`, optional `degraded`, and optional `usage` (tokens + `estimated_cost_usd` when usage is available).

## Estimation domain guardrail

The API is restricted to software/project estimation requests.

- In-domain requests continue through the provider chain as usual.
- Out-of-domain prompts are rejected before provider calls.
- Out-of-domain responses return `422` with:

```json
{
  "detail": {
    "code": "out_of_domain",
    "message": "Only software/project estimation requests are supported."
  }
}
```

Guardrail toggle:

- `LLM_DOMAIN_GUARDRAIL_ENABLED=true` (default): enforce out-of-domain rejection.
- `LLM_DOMAIN_GUARDRAIL_ENABLED=false`: bypass guardrail checks (the request still goes through prompt instructions and providers).

## Adaptive estimation mode

**Main idea:** choose the mode by **decision context**, not only by transcript length.

| Mode | Primary purpose |
|------|------------------|
| `basic` | Quick sizing, initial discovery |
| `standard` | Internal planning (default when the engine does not downgrade) |
| `professional` | Presales and client-facing proposals |
| `expert_review` | Validation, risk surfacing, and high-stakes decisions (same idea as an **EXPERT** review pass) |

The service classifies each request and routes it to one output depth mode (`basic`, `standard`, `professional`, or `expert_review`). With `DEV_MODE=true`, the selected mode is returned in the `mode` field together with routing metadata (`assessment`, `mode_eligibility`). Routing is deterministic and service-level (not an extra endpoint, and not a second classifier model call in v1).

Mode-specific system instructions live as plain text files under `app/context/prompts/` (`basic.txt`, `standard.txt`, `professional.txt`, `expert_review.txt`). Edit those files to tune wording and output contracts without changing Python code.

Mode intent and expected output (reference):

| Mode | Use case | Input quality | Typical output |
|------|----------|---------------|----------------|
| `basic` | very early idea | low | MVP scope, assumptions, effort range, key risks |
| `standard` | default product estimation | medium | scope by areas, task table, risks, sprint-oriented plan |
| `professional` | presales / client proposal | high | in/out of scope, modules, dependencies, effort scenarios |
| `expert_review` | high-stakes decision | expert | gaps, scenarios, cost drivers, recommendations, confidence |

Business rule: mode escalation is based on context quality, not only on input length.

If the request lacks enough context, premium modes should be downgraded with an explicit warning rather than returning false precision.

### Response metadata (detailed)

With **`DEV_MODE=false`** (default), the JSON body is minimal: **`estimation`**, a deterministic **`score`** in `[0, 1]` from the **generated markdown** (estimator-compatible structural checks), plus **`degraded`** when the static fallback path produced the text (so callers are not misled into treating it as a live model output).

With **`DEV_MODE=true`**, the response additionally includes operational and debugging fields:

- **Routing and provider:** `mode`, `model`, `provider`, optional `assessment`, optional `mode_eligibility`
- **Request correlation:** `request_id`, `timestamp`, `latency_ms`
- **Reproducibility:** `prompt_version`, `examples_version` (trace prompt/example changes vs model or infra changes)
- **Usage (when the provider returns token counts):** `usage` with `prompt_tokens`, `completion_tokens`, `total_tokens`, `preprocessing_input_tokens`, `preprocessing_output_tokens` (from the provider when present, otherwise `0`), and optional `estimated_cost_usd`

`degraded` may appear in either mode when static fallback is used.

#### Cost estimation notes

- Cost is an approximation (not billing source of truth).
- Cost appears only if:
  - `DEV_MODE=true`
  - provider returns token usage
  - model pricing is configured in the API
- If any of the above is missing, `usage.estimated_cost_usd` is `null`.

#### Versioning guidelines

`prompt_version` and `examples_version` are returned in the API body only when `DEV_MODE=true` (they still exist in code for observability and future use).

Update metadata versions whenever behavior-affecting inputs change:

- Bump `prompt_version` when prompt instructions/format/constraints change.
- Bump `examples_version` when the few-shot pool, per-mode layout, or sampling rules change (`app/context/examples/<mode>/` files or `app/context/examples.py`).

Suggested convention:

- `v1`, `v2`, `v3`, `v4`, … for major behavioral changes
- `v1.1`, `v1.2` for incremental tuning

## Tests

```bash
cd proyectos/estimador-cag
uv run pytest
```

No real OpenAI calls: the suite mocks the provider client.

## Configuration

See `.env.example` for variable names.

Provider chain behavior:

- `LLM_PROVIDERS` defines the ordered fallback chain (default `openai,anthropic`).
- Providers without credentials are skipped with structured logs.
- `STATIC_FALLBACK_ENABLED=true` appends a deterministic local fallback response (`provider="static_fallback"` and `degraded=true`).
- `LLM_AUTH_FALLBACK=false` keeps auth/config failures explicit by default (returns `503` instead of silently falling back).
- `LLM_DOMAIN_GUARDRAIL_ENABLED=true` enables pre-provider domain rejection for non-estimation prompts.

Required for at least one live provider:

- `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY`

Optional overrides include `OPENAI_MODEL`, `OPENAI_TIMEOUT_SECONDS`, `ANTHROPIC_MODEL`, `ANTHROPIC_TIMEOUT_SECONDS`, per-mode `ESTIMATION_<MODE>_OUTPUT_TOKENS_MAX` (completion length cap; see `.env.example`), `DEV_MODE` (set `true` to include mode, provider, timing, versions, routing assessment, token usage, and approximate cost), `FORCED_ESTIMATION_MODE` (set to `basic`, `standard`, `professional`, or `expert_review` to skip adaptive routing; leave empty for default behavior), and `ESTIMATION_OUTPUT_PERSIST_ENABLED` (set `true` to persist successful `200` estimate outputs to markdown files under `output-responses/`).

When `ESTIMATION_OUTPUT_PERSIST_ENABLED=true`, each successful `POST /api/v1/estimate` writes the `estimation` field into:

- `output-responses/response-YYYYmmdd-hhmmss.md` (UTC timestamp).

When `ESTIMATION_STATS_LOG_ENABLED=true`, each successful `POST /api/v1/estimate` appends one NDJSON line (metadata only, no estimation body) for usage analytics. The default file is `output-stats/estimation-stats.jsonl` at the monorepo root; override with `ESTIMATION_STATS_LOG_PATH` (absolute path). Failures to write the log are logged as warnings and do not fail the request.

### Response examples by environment mode

With `DEV_MODE=false` (live provider):

```json
{
  "estimation": "## Estimation: ...",
  "score": 0.6125
}
```

With `DEV_MODE=false` and static fallback (`degraded`):

```json
{
  "estimation": "## Estimation: ...",
  "score": 0.35,
  "degraded": true
}
```

With `DEV_MODE=true`:

```json
{
  "estimation": "## Estimation: ...",
  "mode": "standard",
  "model": "gpt-4o-mini",
  "provider": "openai",
  "request_id": "est_abc123def456",
  "timestamp": "2026-04-27T10:00:00Z",
  "latency_ms": 1800,
  "prompt_version": "v6",
  "examples_version": "file-mode-v4-estimator-layout",
  "score": 0.6125,
  "usage": {
    "prompt_tokens": 920,
    "completion_tokens": 410,
    "total_tokens": 1330,
    "preprocessing_input_tokens": 0,
    "preprocessing_output_tokens": 0,
    "estimated_cost_usd": 0.000384
  }
}
```
