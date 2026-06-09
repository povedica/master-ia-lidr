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

## Documentation Plan

- README:
  - add `POST /api/v1/search` request/response examples
  - explain cosine distance vs L2/inner product
  - explicitly state that there is no vector index yet
  - state that for hundreds of chunks sequential scan is acceptable as a baseline
- Technical docs (`docs/technical/README.md` §23):
  - search module layout, HTTP contract, verification commands
- Architecture HTML (`docs/arquitectura-estimador-cag.html`):
  - search router node, API table row, feature-038 milestone note
- Second Brain:
  - `learnings/docs/sesiones/sesion-07-semantic-search-endpoint.md`
  - operator choice and alignment with future `vector_cosine_ops`

## Implementation Plan

- [x] Step 1: Add search schemas and validation tests.
- [x] Step 2: Add repository/service query with pgvector `cosine_distance`.
- [x] Step 3: Add router and register it in `app/main.py`.
- [x] Step 4: Add service/router tests with fake embedder and seeded chunks.
- [x] Step 5: Run manual ingest + search smoke check.
- [x] Step 6: Update README, technical docs, architecture HTML, and Second Brain notes.

## Learnings

- Cosine distance is used because it aligns with common RAG literature and the future `vector_cosine_ops` index path. In SQLAlchemy/pgvector it compiles to the `<=>` operator.
- The absence of an index is a teaching point: it provides a visible baseline before optimizing.
- Search must reuse the same embedding model as ingest; otherwise distance comparisons become meaningless.
- **Semantic ≠ keyword:** a query mentioning SAML can still rank OAuth chunks highly if “authentication” and “API” dominate the embedding signal — the corpus may contain no SAML text at all.
- **Duplicate ingests inflate results:** repeated `source_path` inserts produce identical chunks with different `chunk_id`/`document_id` values; they can occupy multiple top-k slots with the same distance.
- **Distance interpretation:** values around 0.65–0.71 on a small course corpus indicate moderate similarity, not a strong match. Lower is better; near-zero would indicate a very close hit.
- **Multi-signal queries:** when a query mixes sector (“education”) and technical terms (“REST API”, “authentication”), ranking reflects a trade-off between signals — the best sector match may appear at #3 while auth/API chunks lead.

## Manual query analysis (verified on Compose Postgres)

This section records a real end-to-end search against the persisted corpus (2026-06-09). It demonstrates how to read `distance`, metadata, and ranking when the query does not exactly match any chunk.

### Request

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/search \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "REST API with SAML authentication for public educational sector",
    "k": 5
  }'
```

### Observed response (summary)

| Rank | chunk_id | document_id | budget_id | client_sector | distance | Component (abbrev.) |
|------|----------|-------------|-----------|---------------|----------|---------------------|
| 1 | 1 | 2 | BUD-2024-014 | finance | 0.6529 | OAuth 2.0 authentication backend |
| 2 | 25 | 15 | BUD-2024-014 | finance | 0.6529 | OAuth 2.0 authentication backend (duplicate ingest) |
| 3 | 7 | 7 | BUD-2024-045 | education | 0.6529 | Course catalog API |
| 4 | 8 | 7 | BUD-2024-045 | education | 0.6912 | SCORM package importer |
| 5 | 9 | 7 | BUD-2024-045 | education | 0.7069 | Learner progress dashboard |

`search_time_ms` was ~276–372 ms (includes one OpenAI `embed_one` call plus Postgres sequential scan).

### How to read this result

**Query intent vs corpus content**

The query asks for REST API + SAML + authentication + public educational sector. The persisted corpus contains OAuth/JWT fintech components and LMS/education components, but **no chunk mentions SAML explicitly**. Semantic search returns the closest vectors, not keyword matches.

**Why OAuth fintech ranks #1 and #2**

The top slots are `BUD-2024-014` (FintechCorp, sector `finance`): “OAuth 2.0 authentication backend” for a mobile banking API. The embedder strongly associates the query’s “REST API” and “authentication” with OAuth/JWT/API language. Sector “education” in the query is weaker than the auth/API signal for those vectors.

**Why #1 and #2 are identical**

Same budget ingested twice (`chunk_id` 1 and 25, different `document_id`). Same content → same embedding → same distance. This is a **data-quality artifact**, not a ranking bug. Operational follow-up: deduplicate by `source_path` at ingest time or filter duplicates in search (out of scope for feature-038).

**Why education appears at #3**

`BUD-2024-045` (Corporate LMS, sector `education`) — “Course catalog API” with CRUD and role-based access — almost ties with OAuth on distance (~0.6529) but aligns better with “public educational sector” + “REST API”. It is the most intent-aligned result despite ranking third.

**Why SCORM and dashboard follow**

Same education budget; progressively weaker match to “API + SAML + auth”. Distances increase (0.691 → 0.707), showing descending semantic relevance.

**Takeaways for operators and RAG design**

1. Inspect `distance` magnitude, not only rank — all five results here are moderate matches (0.65–0.71), not strong hits (~0.2–0.3).
2. Expect semantic confusion between related auth protocols (SAML vs OAuth) when the corpus lacks the exact term.
3. Plan for deduplication or `source_path` uniqueness enforcement before production retrieval.
4. Future increments (feature-039 script, metadata filters, hybrid search) can make this behaviour easier to demonstrate and tune.

### Contrasting query (OAuth + fintech — closer intent match)

When the query aligns with corpus vocabulary, distances drop and the top result is clearly relevant:

```json
{
  "query": "REST API with OAuth authentication for fintech sector",
  "k": 5
}
```

The top result is the same `BUD-2024-014` OAuth component with distance ~0.42 — noticeably lower than the SAML/education query, reflecting a stronger semantic match.

## Retrospective

1. **Process:** TDD honoured — schema tests RED before models; repository/service/router tested with fakes before manual smoke.
2. **Technical:** Reused `OpenAIEmbedder`, `get_db_session`, and ingest-router DI patterns; SQL isolated in `SemanticSearchRepository`.
3. **Quality:** 20 targeted tests; full suite green; manual curl on Compose confirmed real retrieval.
4. **Docs:** README, `docs/technical/README.md`, architecture HTML, and this work item updated; feature-039 remains for scripted multi-query examples.

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

- https://github.com/povedica/master-ia-lidr/pull/34 — merged via `/finish-task`

## Repository commits (master-ia)

| Commit | Summary |
|--------|---------|
| d2ac246 | docs(work-items): add feature-038 semantic search endpoint spec |
| 510335c | test(embedding-pipeline): add search schema validation tests (RED→GREEN) |
| 1c212a2 | feat(embedding-pipeline): add semantic search repository and service |
| e21cc10 | feat(search): add POST /api/v1/search semantic search endpoint |
| 2e9046f | docs(work-items): record feature-038 verification and acceptance status |
| b07c130 | docs(work-items): add commit SHAs to feature-038 report |
| (finish-task) | docs: feature-038 manual analysis, technical docs, architecture, learnings |

## Verification

- **Verified (automated):** `uv run pytest tests/embedding_pipeline/test_search_*.py` — 20 passed; full suite `uv run pytest` — 494+ passed, 11 skipped.
- **Verified (manual):** `curl -X POST http://127.0.0.1:8000/api/v1/search` against Compose Postgres — ranked results with cosine distances; SAML/education query analysis documented above.
- **Not verified:** five-query demonstration script (`feature-039` scope); `output_examples.txt`.
- **Residual risk:** no integration test against real Postgres in CI (repository SQL validated via compile + mocked session); duplicate ingests can occupy multiple top-k slots.
