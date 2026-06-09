# Feature: Transactional Persistent Ingest for Budget Embeddings

> Increment 2 of 4 for the production-like semantic search milestone.
> Depends on: `feature-036-postgres-pgvector-alembic-baseline`.

## Objective

Refactor `POST /api/v1/embeddings/ingest` from an in-memory prototype into a production-like ingest endpoint that persists one source budget document, its chunks, and their embeddings in Postgres in a single transaction.

The endpoint should stop returning raw vectors and instead return ingestion metadata that proves the document was stored consistently.

## Context

- Current endpoint: `app/routers/embeddings.py` exposes `POST /api/v1/embeddings/ingest`.
- Current request/response:
  - `IngestRequest` contains `budgets: list[Budget]`.
  - `IngestResponse` returns `chunks: list[EmbeddedChunk]` and `stats`.
- Current orchestration lives in `app/embedding_pipeline/ingest.py`:
  - `JSONStructuralChunker.chunk(budgets)`
  - `OpenAIEmbedder.embed_many(chunks)`
  - return embedded chunks in memory.
- `OpenAIEmbedder` already supports batched `embed_many()` and validates `1536`-dimension vectors.
- The exercise now expects persistence by `source_path`, duplicate handling, and atomic document + chunks writes.
- `feature-036` supplies Postgres, pgvector, Alembic, SQLAlchemy async, `documents`, and `chunks`.

## Scope

### Includes

- Introduce a persisted ingest request/response contract:
  - request: `source_path`, `document_type`, `content`
  - response: `document_id`, `chunks_created`, `embedding_dimension`, `ingestion_time_ms`
- Refactor the ingest path so it:
  - checks duplicate `source_path`
  - inserts a `documents` row
  - validates/chunks the budget content
  - embeds chunk texts in batches
  - inserts all `chunks` rows with embeddings
  - commits only if the full flow succeeds
- Return `409 Conflict` when `source_path` already exists.
- Add service/repository boundaries so the router does not contain SQL or provider SDK details.
- Add deterministic tests with fake embedder/session behavior where possible.
- Update README endpoint docs for the new persisted contract.

### Excludes

- Adding `POST /api/v1/search`.
- Returning raw vectors from the ingest endpoint.
- Implementing async job/polling semantics.
- Supporting multi-file directory ingest.
- Adding vector indexes, metadata filters, hybrid search, or tuning.
- Calling real OpenAI in routine tests.

## Functional Requirements

### Request

Effective route remains versioned:

```text
POST /api/v1/embeddings/ingest
```

Request body:

```json
{
  "source_path": "data/budgets/budget_2024_q1_fintech.json",
  "document_type": "historical_budget",
  "content": {
    "budget_id": "budget_2024_q1_fintech",
    "client_metadata": {
      "name": "Example Client",
      "sector": "fintech",
      "country": "ES"
    },
    "project_summary": "REST API for a fintech mobile app",
    "main_technology": "python",
    "year": 2024,
    "total_estimated_hours": 120,
    "components": []
  }
}
```

`content` must be validated against the existing `Budget` schema before chunking. The service can wrap the parsed budget as `[budget]` when calling the existing `JSONStructuralChunker`.

### Response

Successful response:

```json
{
  "document_id": 42,
  "chunks_created": 17,
  "embedding_dimension": 1536,
  "ingestion_time_ms": 1240
}
```

Duplicate response:

```json
{
  "detail": "Document already ingested",
  "document_id": 42
}
```

### Behavior

- If `documents.source_path` already exists, return `409 Conflict` and do not call the embedder.
- If budget validation fails, return FastAPI/Pydantic validation errors or a safe `422` response.
- If embedding fails, no `documents` or `chunks` rows are committed.
- If chunk insertion fails, no `documents` row is committed.
- If the budget has zero components, store the document and return `chunks_created: 0` with no embedding call.
- Logs must include safe context such as `source_path`, `document_type`, `request_id`, and `error_type`; logs must not include secrets or full prompts containing sensitive data.

## Technical Approach

### Schemas

Update or add Pydantic schemas in `app/embedding_pipeline/schemas.py`:

- `PersistentIngestRequest`
  - `source_path: str`
  - `document_type: str`
  - `content: Budget`
  - optional `metadata: dict[str, object] = {}`
- `PersistentIngestResponse`
  - `document_id: int`
  - `chunks_created: int`
  - `embedding_dimension: int`
  - `ingestion_time_ms: int`

Keep old schema names only if tests or docs still need them during the refactor. The public endpoint should use the new persisted contract.

### Service Boundary

Create a service such as `app/embedding_pipeline/persistent_ingest.py` or `app/services/embedding_ingest_service.py`.

The router should:

- create dependencies for `JSONStructuralChunker`, `OpenAIEmbedder`, and DB session
- call one service function/method
- map domain duplicate error to `409`
- map unexpected errors to safe `500`

The service should own the transaction:

1. Start async transaction.
2. Query `documents` by `source_path`.
3. Insert `documents`.
4. Chunk `request.content`.
5. If chunks exist, call `embedder.embed_many(chunks)`.
6. Insert chunk rows with:
   - `document_id`
   - `chunk_type` such as `budget_component`
   - `content = embedded.text`
   - `embedding = embedded.embedding`
   - `metadata = embedded.metadata`
7. Commit.

### Duplicate Handling

Use both:

- application-level pre-check for a clear `document_id` in the `409` response
- database uniqueness on `source_path` from `feature-036` to protect concurrent requests

If a unique constraint race occurs, convert it to the same safe duplicate response where practical.

## Acceptance Criteria

- [x] AC-01: `POST /api/v1/embeddings/ingest` uses the persisted ingest request contract with `source_path`, `document_type`, and `content`.
- [x] AC-02: Successful ingest inserts exactly one row in `documents`.
- [x] AC-03: Successful ingest inserts one `chunks` row per budget component.
- [x] AC-04: Inserted chunks store `content`, `metadata`, `chunk_type`, and `Vector(1536)` embeddings.
- [x] AC-05: The endpoint response contains `document_id`, `chunks_created`, `embedding_dimension`, and `ingestion_time_ms`, and does not include raw vectors.
- [x] AC-06: Duplicate `source_path` returns `409 Conflict` with `"Document already ingested"` and the existing `document_id`.
- [x] AC-07: Duplicate requests do not call `OpenAIEmbedder`.
- [x] AC-08: A simulated embedder failure rolls back the full transaction and leaves no partial document/chunk rows.
- [x] AC-09: A simulated chunk insert failure rolls back the full transaction and leaves no orphan document row.
- [x] AC-10: Zero-component budgets persist the document with zero chunks and skip the embedding call.
- [x] AC-11: Router code does not contain SQL statements or OpenAI SDK calls.
- [x] AC-12: Existing embedding/chunker unit tests remain green after the contract refactor is reflected in router tests.

## Test Plan

- Unit tests:
  - persisted ingest schema validation
  - duplicate domain error mapping
  - timing/response assembly without real OpenAI
- Service tests:
  - fake embedder returns deterministic 1536-dimensional vectors
  - successful ingest persists document + chunks
  - duplicate `source_path` returns duplicate error and embedder call count is zero
  - embedder failure rolls back
  - zero-component budget stores only the document
- Router tests:
  - `200` success with fake embedder and test DB/session dependency
  - `409` duplicate
  - `422` invalid content
  - safe `500` on unexpected service error
- Manual checks:
  - start Compose stack
  - run migration
  - POST one budget JSON
  - query `documents` and `chunks` counts from Postgres
  - repeat the same `source_path` and confirm `409`

## Verification

- Automated (verified 2026-06-09, re-run at task closure):
  - `uv run pytest tests/embedding_pipeline/test_router.py` — 8 passed
  - `uv run pytest tests/embedding_pipeline/test_persistent_ingest_service.py` — 6 passed
  - `uv run pytest tests/embedding_pipeline/` — 95 passed
  - `uv run pytest` — 474 passed, 12 deselected (`slow`)
- Manual (verified 2026-06-09):
  - `docker compose` Postgres healthy; `uv run alembic upgrade head`
  - Zero-component `curl` ingest → `200` with `chunks_created: 0`; row in `documents`
  - Repeat same `source_path` → `409` with existing `document_id`
  - Full fixture batch via `dev-tools/ingest_budget_fixtures.py --skip-existing` (see below)
- Not verified yet:
  - semantic search over persisted chunks (feature-038)
  - query examples script (feature-039)
  - unique-constraint race → `409` under concurrent duplicate `source_path` requests

## Documentation Plan

- README:
  - replace the prototype ingest response with the persisted response
  - document `409 Conflict` duplicate behavior
  - document atomic transaction behavior
  - keep the route shown as `POST /api/v1/embeddings/ingest`
- Second Brain:
  - record why raw vectors are no longer returned by the production-like endpoint
  - record transaction reasoning and duplicate strategy

## Implementation Plan

- [x] Step 1: Add persisted ingest schemas and update router contract tests.
- [x] Step 2: Add repository/service boundaries for documents and chunks.
- [x] Step 3: Implement successful transaction path with fake embedder tests.
- [x] Step 4: Implement duplicate `source_path` handling and `409` mapping.
- [x] Step 5: Add rollback tests for embedder and insert failures.
- [x] Step 6: Update README and architecture HTML.
- [x] Step 7: Run focused tests and manual Compose/Postgres ingest check.
- [x] Follow-up: `dev-tools/ingest_budget_fixtures.py` for batch fixture ingest over HTTP.

## Learnings

- This is the vertical slice where the prototype becomes stateful: the same chunker and embedder remain useful, but the public API changes from "return vectors" to "persist a searchable corpus".
- The transaction boundary is the central correctness property: document, chunks, and embeddings either all exist together or none of them do.
- Duplicate handling belongs at both application and database levels because concurrent requests can bypass a pre-check.
- `documents.metadata` is only populated when the client sends the optional request field; chunk metadata is always produced by `JSONStructuralChunker`. Dev batch ingest fills document metadata from budget fields for easier inspection.
- Embed-before-insert ordering avoids orphan documents when OpenAI fails, without relying on rollback after a document row is flushed.

## Fixture batch ingest report (manual, 2026-06-09)

Command:

```bash
uv run python dev-tools/ingest_budget_fixtures.py --skip-existing
```

Source directory: `tests/embedding_pipeline/fixtures/budget_files/` (13 valid `*.json`; `invalids/` excluded).

| File | HTTP | document_id | chunks_created | Notes |
|------|------|-------------|----------------|-------|
| bud-2023-078.json | 200 | 3 | 2 | |
| bud-2024-000.json | 200 | 4 | 0 | zero components |
| bud-2024-014.json | 409 | 2 | — | duplicate (`--skip-existing`) |
| bud-2024-021.json | 200 | 5 | 2 | |
| bud-2024-032.json | 200 | 6 | 1 | |
| bud-2024-045.json | 200 | 7 | 3 | |
| bud-2024-056.json | 200 | 8 | 3 | |
| bud-2024-067.json | 200 | 9 | 4 | |
| bud-2024-099.json | 200 | 10 | 2 | |
| bud-2025-003.json | 200 | 11 | 2 | |
| bud-2025-011.json | 200 | 12 | 1 | |
| bud-2025-019.json | 200 | 13 | 1 | |
| bud-2025-024.json | 200 | 14 | 2 | |

Summary: **12 ingested**, **1 skipped (409)**, **0 failed** of 13 fixtures.

Postgres counts after batch (included prior manual smoke rows):

```text
documents: 14
chunks:    24
```

Script options: `--dry-run`, `--base-url`, `--skip-existing`, `--budgets-dir`.

## Estimation

- Size: M
- Estimated time: 3–4 hours
- Planned steps: 7

## Implementation progress

- [x] Step 1: Persisted ingest schemas and schema unit tests
- [x] Step 2: Repository layer and duplicate domain error
- [x] Step 3: Persistent ingest service — successful transaction path
- [x] Step 4: Router wiring, DB session dependency, 409 mapping
- [x] Step 5: Rollback tests (embedder failure, chunk insert failure)
- [x] Step 6: Update milestone/router tests, README, architecture HTML
- [x] Step 7: Full pytest pass and manual Compose verification

## Repository commits (master-ia)

| Commit | Summary |
|--------|---------|
| `26beecb` | docs(feature-037): add transactional persistent ingest work item |
| `fc4a876` | feat(embedding): add persisted ingest request/response schemas |
| `f255457` | feat(embedding): add transactional persistent ingest service |
| `064de6e` | feat(embedding): wire persisted ingest endpoint with DB session |
| `9badd1b` | docs(feature-037): document persisted ingest contract and architecture |
| `d47863e` | docs(feature-037): record verification evidence for persisted ingest |
| (closure) | chore(dev-tools): add ingest_budget_fixtures batch HTTP helper |

## Pull Request

- https://github.com/povedica/master-ia-lidr/pull/33 — merged at task closure (2026-06-09)
