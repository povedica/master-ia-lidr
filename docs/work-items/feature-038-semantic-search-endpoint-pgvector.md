# Feature: Semantic Search Endpoint over Persisted pgvector Chunks

> Increment 3 of 4 for the production-like semantic search milestone.
> Depends on: `feature-036-postgres-pgvector-alembic-baseline` and `feature-037-transactional-persistent-embedding-ingest`.

## Objective

Add a semantic search API that embeds a user query with the same embedding model used during ingest and retrieves the top-k persisted chunks from Postgres using pgvector `cosine_distance`.

This increment makes the persisted corpus useful through a stable HTTP contract while deliberately keeping the implementation simple: no vector index, no metadata filters, no hybrid search.

## Context

- `feature-036` creates Postgres + pgvector schema with `documents` and `chunks`.
- `feature-037` persists documents, chunks, and embeddings transactionally.
- The embedder already exposes `OpenAIEmbedder.embed_one(text)` and validates `1536`-dimensional vectors.
- Existing FastAPI conventions register routers under `/api/v1`.
- The exercise's functional endpoint is described as `POST /search`; in this repo the effective path should be versioned as `POST /api/v1/search` unless `/search` is explicitly required as an additional alias.
- The official exercise expects ranking by cosine distance and a sequential-scan baseline before future vector-index work.

## Scope

### Includes

- Add search request/response schemas.
- Add a search router or register a route under the existing embeddings router, keeping code small and clear.
- Add a search service that:
  - embeds the query with `OpenAIEmbedder.embed_one()`
  - queries persisted `chunks`
  - computes `Chunk.embedding.cosine_distance(query_vector).label("distance")`
  - orders by `distance`
  - limits by `k`
  - returns user-facing result models
- Add deterministic tests with fake embedder vectors and seeded DB rows.
- Add safe error handling for provider and database failures.
- Update README API docs.

### Excludes

- Vector indexes such as HNSW or IVFFlat.
- Metadata filters.
- Hybrid keyword + vector search.
- Search result reranking.
- Pagination.
- Real OpenAI calls in default tests.
- Changing the ingest transaction logic except where shared dependencies are needed.

## Functional Requirements

### Request

Effective route:

```text
POST /api/v1/search
```

Request body:

```json
{
  "query": "REST API with OAuth authentication for fintech sector",
  "k": 5
}
```

Validation:

- `query`: non-empty string after trimming.
- `k`: integer, default `5`, minimum `1`, maximum conservative bound such as `20` or `50`.

### Response

```json
{
  "query": "REST API with OAuth authentication for fintech sector",
  "k": 5,
  "search_time_ms": 87,
  "results": [
    {
      "chunk_id": 156,
      "document_id": 12,
      "chunk_type": "budget_component",
      "content": "Backend service implementation with JWT-based authentication...",
      "distance": 0.231,
      "metadata": {
        "scope": "backend",
        "technologies": ["python", "fastapi"]
      }
    }
  ]
}
```

Behavior:

- If the corpus is empty, return `200` with `results: []`.
- Only chunks with non-null embeddings should be eligible for ranking.
- Results must be sorted ascending by `distance`.
- The same embedding model configured for ingest must be used for search.
- Logs must include safe request metadata such as `request_id`, `k`, and result count, not API keys or full sensitive payloads.

## Technical Approach

### Schemas

Add to `app/embedding_pipeline/schemas.py` or a search-specific module:

- `SearchRequest`
  - `query: str`
  - `k: int = Field(default=5, ge=1, le=50)`
- `SearchResult`
  - `chunk_id: int`
  - `document_id: int`
  - `chunk_type: str`
  - `content: str`
  - `distance: float`
  - `metadata: dict[str, object]`
- `SearchResponse`
  - `query: str`
  - `k: int`
  - `search_time_ms: int`
  - `results: list[SearchResult]`

### Router and Services

Preferred layout:

- `app/routers/search.py`
  - `@router.post("/search", response_model=SearchResponse)`
  - dependency wiring for DB session and `OpenAIEmbedder`
  - maps service errors to safe HTTP errors
- `app/embedding_pipeline/search.py` or `app/services/semantic_search_service.py`
  - owns query embedding and search orchestration
- repository function for pgvector SQL expression if this keeps SQL out of service code

`app/main.py` should register the router with `/api/v1`.

### Query

Use SQLAlchemy with pgvector:

- select:
  - chunk id
  - document id
  - chunk type
  - content
  - metadata
  - cosine distance label
- where:
  - `embedding IS NOT NULL`
- order:
  - ascending distance
- limit:
  - `request.k`

The query must use `cosine_distance` to align with the future `vector_cosine_ops` HNSW path, even though no index is created in this feature.

## Acceptance Criteria

- [x] AC-01: `POST /api/v1/search` appears in OpenAPI.
- [x] AC-02: Valid search request returns `200` with `query`, `k`, `search_time_ms`, and `results`.
- [x] AC-03: The service calls `OpenAIEmbedder.embed_one()` exactly once per search request.
- [x] AC-04: The SQL query ranks chunks by `cosine_distance` ascending.
- [x] AC-05: Response result objects include `chunk_id`, `document_id`, `chunk_type`, `content`, `distance`, and `metadata`.
- [x] AC-06: `k` limits the number of returned results.
- [x] AC-07: Empty corpus returns `200` with `results: []`.
- [x] AC-08: Chunks with `embedding = NULL` are not returned.
- [x] AC-09: Invalid `query` or `k` returns `422`.
- [x] AC-10: Provider/database errors return safe API errors and log structured context without secrets.
- [x] AC-11: No vector index is added by this feature.
- [x] AC-12: README explains why cosine distance is used and why sequential scan is acceptable for the course corpus size.

## Test Plan

- Unit tests:
  - request validation for empty query and `k` bounds
  - response model serialization
- Service/repository tests:
  - seed chunks with controlled vectors
  - fake query embedding
  - assert returned order by distance
  - assert `k` limit
  - assert null embeddings are excluded
  - assert empty corpus returns empty list
- Router tests:
  - OpenAPI route exists
  - success with fake embedder
  - validation failures return `422`
  - service failure maps to safe `500`
- Manual checks:
  - run Compose + migration
  - ingest at least one budget through `feature-037`
  - call `/api/v1/search`
  - compare top results and distances in the response

## Verification

- Automated:
  - targeted search tests — **20 passed**
  - existing embedding pipeline tests — **included in full suite**
  - `uv run pytest` — **494 passed, 11 skipped**
- Manual:
  - `docker compose up --build` — app already running
  - `uv run alembic upgrade head` — schema present in Compose Postgres
  - ingest fixture budget — corpus already populated
  - `curl -X POST http://127.0.0.1:8000/api/v1/search ...` — **200 with ranked results**
- Not verified yet:
  - five-query demonstration script (`feature-039`)
  - `output_examples.txt`

## Documentation Plan

- README:
  - add `POST /api/v1/search` request/response examples
  - explain cosine distance vs L2/inner product
  - explicitly state that there is no vector index yet
  - state that for hundreds of chunks sequential scan is acceptable as a baseline
- Second Brain:
  - record the operator choice and how it aligns with future `vector_cosine_ops`.

## Implementation Plan

- [ ] Step 1: Add search schemas and validation tests.
- [ ] Step 2: Add repository/service query with pgvector `cosine_distance`.
- [ ] Step 3: Add router and register it in `app/main.py`.
- [ ] Step 4: Add service/router tests with fake embedder and seeded chunks.
- [ ] Step 5: Run manual ingest + search smoke check.
- [ ] Step 6: Update README and Second Brain notes.

## Learnings

- Cosine distance is used because it aligns with common RAG literature and the future `vector_cosine_ops` index path.
- The absence of an index is a teaching point: it provides a visible baseline before optimizing.
- Search must reuse the same embedding model as ingest; otherwise distance comparisons become meaningless.

## Estimation

- Size: M
- Estimated time: 3 hours
- Planned steps: 6

## Implementation progress

- [x] Step 1: Search schemas and validation tests
- [x] Step 2: Search repository with pgvector `cosine_distance`
- [x] Step 3: Search service orchestration and unit tests
- [x] Step 4: Search router, `main.py` registration, router tests
- [x] Step 5: README API docs (cosine distance, sequential scan baseline)
- [x] Step 6: Manual ingest + search smoke check

## Pull Request

- https://github.com/povedica/master-ia-lidr/pull/34 (draft, label `wip`)

## Repository commits (master-ia)

| Commit | Summary |
|--------|---------|
| (pending push) | docs(work-items): add feature-038 semantic search endpoint spec |
| (pending push) | test(embedding-pipeline): add search schema validation tests (RED→GREEN) |
| (pending push) | feat(embedding-pipeline): add semantic search repository and service |
| (pending push) | feat(search): add POST /api/v1/search semantic search endpoint |

## Verification

- **Verified (automated):** `uv run pytest tests/embedding_pipeline/test_search_*.py` — 20 passed; full suite `uv run pytest` — 494 passed, 11 skipped.
- **Verified (manual):** `curl -X POST http://127.0.0.1:8000/api/v1/search` against Compose Postgres returned ranked results with cosine distances.
- **Not verified:** five-query demonstration script (`feature-039` scope); `output_examples.txt`.
- **Residual risk:** no integration test against real Postgres in CI (repository SQL validated via compile + mocked session).
