# Estimador CAG

FastAPI service that turns a meeting transcription into a structured software estimate using **Context-Augmented Generation (CAG)**: static few-shot examples live in `app/context/examples.py` and are injected into the system prompt; the live meeting text is sent as the user message.

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

## Run the API

```bash
cd proyectos/estimador-cag
uv run uvicorn app.main:app --reload
```

- Root: `GET http://127.0.0.1:8000/` (JSON pointers to docs and routes)
- Health: `GET http://127.0.0.1:8000/health`
- OpenAPI: `http://127.0.0.1:8000/docs`

Browsers may request `/favicon.ico`; there is no favicon asset, so that request may return 404 and can be ignored.

## Example request

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/estimate \
  -H "Content-Type: application/json" \
  -d '{"transcription":"The client needs a REST API for orders with idempotent POST."}'
```

## Tests

```bash
cd proyectos/estimador-cag
uv run pytest
```

No real OpenAI calls: the suite mocks the provider client.

## Configuration

See `.env.example` for variable names. Required for live estimates:

- `OPENAI_API_KEY`

Optional overrides include `OPENAI_MODEL` (default `gpt-4o-mini`) and `OPENAI_TIMEOUT_SECONDS`.
