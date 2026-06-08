# Feature: FastAPI Ingest Endpoint for Embedding Pipeline

> Increment 4 of 5 for the minimal embedding pipeline (Session 07).
> Depends on: `feature-030` (schemas), `feature-031` (chunker), `feature-032` (embedder).

## Objective

Expose the pipeline over HTTP: implement the ingest endpoint that chunks input budgets, embeds the chunks, and returns `EmbeddedChunk` objects plus aggregate stats. Register the router in `app/main.py`.

## Context

- Building blocks exist: `JSONStructuralChunker` (`feature-031`), `OpenAIEmbedder` (async, `feature-032`), and schemas (`feature-030`).
- FastAPI convention (rule `02-fastapi-standards`): routes live in `app/routers/`, registered in `app/main.py` via `app.include_router(..., prefix=...)`, with explicit `/api/v1` versioning. Existing routers: `estimations` (`/api/v1`), `estimations_v2` (`/api/v2`), `sessions` (`/api/v1`).
  - Architecture review (HIGH): place the router at **`app/routers/embeddings.py`**, not inside `app/embedding_pipeline/`. The `router.py` stub created in `feature-030` stays an unused stub (or is removed in this increment with a note); the canonical router is under `app/routers/`.
  - Versioning (architecture review, LOW): use prefix `/api/v1`, so the full path is `POST /api/v1/embeddings/ingest`. The exercise's bare `/embeddings/ingest` is versioned to match repo standards; document this in README.
- Handlers are async and call services, not SDKs directly (the embedder is the service boundary).
- Logging: stdlib `logging` + `extra` (no `structlog`).

## Scope

### Includes
- `app/routers/embeddings.py` with `router = APIRouter(tags=["embeddings"])` and `POST /embeddings/ingest`.
- Registration in `app/main.py`: `app.include_router(embeddings.router, prefix="/api/v1")`.
- Dependency wiring for `JSONStructuralChunker` and `OpenAIEmbedder` (via `Depends`/factory using `get_settings`).
- Root-route hint update in `main.py` (optional) listing the new endpoint.

### Excludes
- Chunker/embedder internals (Features 031/032).
- CLI (Feature 034).
- Vector DB persistence (Session 08).
- Auth, rate limiting, pagination, streaming.
- Touching existing routers' behavior.

## Functional Requirements

- Route: `POST /embeddings/ingest`, registered under prefix `/api/v1` → effective `POST /api/v1/embeddings/ingest`.
- Request body: `IngestRequest` (`budgets: list[Budget]`).
- Response body: `IngestResponse` (`chunks: list[EmbeddedChunk]`, `stats: IngestStats`).
- Orchestration inside the handler:
  `chunks = chunker.chunk(request.budgets)` → `embedded = await embedder.embed_many(chunks)` → assemble `IngestResponse`.
- `stats` is built from real counts:
  - `total_budgets = len(request.budgets)`
  - `total_chunks = len(embedded)`
  - `total_tokens = embedder.last_total_tokens`
  - `estimated_cost_usd = embedder.last_cost_usd`
- Status codes:
  - `200`: success with populated `IngestResponse`.
  - `422`: Pydantic validation failure (FastAPI automatic).
  - `500`: any unhandled OpenAI/runtime error — return a generic, safe message to the client; log full details (`error_type`, `request_id`) with `extra`, never leaking keys or stack traces (rule `06`).
- Generate a `request_id` (e.g. `emb_{uuid4().hex[:12]}`) and include it in logs.

Edge cases:
- Empty `budgets` → `200` with `chunks: []` and zeroed stats (no API call, per `feature-032` AC-09).
- A budget with no components contributes zero chunks (consistent with `feature-031`).

## Technical Approach

- `app/routers/embeddings.py`:
  - `import logging`, `from uuid import uuid4`, `from typing import Annotated`.
  - `from fastapi import APIRouter, Depends, HTTPException, status`.
  - `from app.config import Settings, get_settings`.
  - `from app.embedding_pipeline.chunker import JSONStructuralChunker`.
  - `from app.embedding_pipeline.embedder import OpenAIEmbedder`.
  - `from app.embedding_pipeline.schemas import IngestRequest, IngestResponse, IngestStats`.
  - Factory deps: `get_chunker()` and `get_embedder(settings)` (mirrors `get_estimation_service` in `estimations_v2.py`).
  - `@router.post("/embeddings/ingest", response_model=IngestResponse)` async handler with try/except mapping unexpected errors to `HTTPException(500, "Unable to embed budgets.")` after logging.
- `app/main.py`:
  - `from app.routers import ... embeddings`.
  - `app.include_router(embeddings.router, prefix="/api/v1")`.
  - Optionally add `"embeddings": "POST /api/v1/embeddings/ingest"` to `read_root()`.

## Estimation

- Size: S
- Estimated time: 2 hours
- Planned steps: 4

## Implementation progress

- [x] Step 1: RED — `tests/embedding_pipeline/test_router.py` with dependency-override fakes
- [x] Step 2: GREEN — `app/routers/embeddings.py` + registration in `app/main.py`
- [x] Step 3: Full suite + router tests green
- [x] Step 4: README + Second Brain note

## Acceptance Criteria
- [x] AC-01: `POST /api/v1/embeddings/ingest` appears in Swagger UI (`/docs`).
- [x] AC-02: A valid `IngestRequest` with ≥2 budgets returns `200` and a populated `IngestResponse`.
- [x] AC-03: `len(response.chunks)` equals total components across all input budgets.
- [x] AC-04: `response.stats.total_budgets` equals the number of budgets sent.
- [x] AC-05: `response.stats.total_chunks == len(response.chunks)`; `total_tokens` and `estimated_cost_usd` come from the embedder.
- [x] AC-06: Malformed body (missing required fields) returns `422`.
- [x] AC-07: An embedder failure surfaces as `500` with a generic message; full error is logged with `request_id` and `error_type`, no secrets.
- [x] AC-08: Empty `budgets` returns `200` with `chunks: []` and zeroed stats, no API call.
- [x] AC-09: Router lives in `app/routers/embeddings.py` and is registered under `/api/v1`; existing routers are unchanged.

## Test Plan
- Integration tests (`tests/embedding_pipeline/test_router.py`) using FastAPI `TestClient`/httpx ASGITransport with the embedder **mocked/faked** (no real API keys):
  - Inject a fake embedder returning deterministic 1536-vectors via dependency override; assert AC-02..AC-05.
  - Assert `422` on malformed body (AC-06).
  - Override embedder to raise; assert `500` + safe message + log contents via `caplog` (AC-07).
  - Empty budgets path (AC-08).
  - Assert the path is present in `app.openapi()` (AC-01).
- Manual checks: `uv run uvicorn app.main:app --reload`, open `/docs`, POST a 2-budget payload (real key) and confirm counts.

## Verification
- Automated: `uv run pytest tests/embedding_pipeline/test_router.py` — **7 passed** (mocked embedder).
- Full fast suite: `uv run pytest` — **413 passed**, 11 skipped, 10 deselected.
- Manual: Swagger smoke test with a real key; confirm `200`, chunk count, and `total_budgets`. **Not verified yet** in this session.
- Not verified yet: CLI cosine similarity (Feature 034).

## Documentation Plan
- README: document the endpoint path `POST /api/v1/embeddings/ingest`, request/response shape, status codes, and the Docker run command (`docker compose up app` then POST to `http://localhost:8000/api/v1/embeddings/ingest`).
- Second Brain: note the router-location and versioning decisions vs the exercise text.

## Implementation Plan
- [x] Step 1: Create `app/routers/embeddings.py` with deps + handler.
- [x] Step 2: Register router in `app/main.py` (and root hint).
- [x] Step 3: Add `tests/embedding_pipeline/test_router.py` with dependency-override fakes (RED → GREEN).
- [x] Step 4: Run tests; verify `/docs` and error mapping.
- [x] Step 5: Update README + Second Brain note.

## Learnings
- Keeping the router under `app/routers/` and versioning under `/api/v1` preserves the project's single, predictable API surface; co-locating routes inside feature packages would fragment it.
- The 500 handler must convert provider errors to a safe message at the boundary; the embedder already classifies rate limits, so the router only needs a generic catch-all with structured logging.
