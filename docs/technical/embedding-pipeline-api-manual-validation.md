# Embedding Pipeline API — Manual Validation Report

**Date:** 2026-06-09  
**Environment:** Local stack (`http://127.0.0.1:8000`, Postgres via Docker Compose)  
**Scope:** `POST /api/v1/embeddings/ingest`, `POST /api/v1/search`  
**Related features:** feature-037 (persistent ingest), feature-038 (semantic search)

This document records manual HTTP validation of the embedding pipeline ingest and search APIs, including functional scenarios, negative cases, database verification, and concurrency stress tests.

---

## 1. Executive summary

| Area | Result |
|------|--------|
| Invalid request rejection (422) | **Pass** — ingest and search validation behave as documented |
| Valid ingest + Postgres persistence | **Pass** — document and chunk rows created; embedding stored |
| Duplicate `source_path` (sequential) | **Pass** — returns `409` with `document_id` |
| Search finds newly ingested content | **Pass** — top-1 match with low cosine distance |
| Unrelated search excludes new document from top-k | **Pass** — high distances; new doc absent from top-5 |
| Zero-component budget ingest | **Pass** — `chunks_created=0`, no embedder call |
| Concurrent ingest (distinct paths) | **Pass** — 8/8 succeeded with unique `document_id` |
| Concurrent search | **Pass** — 12/12 returned `200` |
| Concurrent duplicate ingest (race) | **Fixed (2026-06-09)** — `IntegrityError` mapped to `409`; see §4.1 and §8 |
| Mixed ingest + search concurrency | **Partial** — searches OK; duplicate ingest race yields `500` |

**Verified:** 17 functional HTTP scenarios + 4 concurrency scenarios against live API and Postgres.  
**Not verified:** behaviour with missing `OPENAI_API_KEY` or `DATABASE_URL`.  
**Residual risk:** test data remains in the dev database. Concurrent duplicate ingest was fixed in `persistent_ingest.py` (§8).

---

## 2. Test environment

| Component | Value |
|-----------|-------|
| API base URL | `http://127.0.0.1:8000` |
| Health check | `GET /health` → `{"status":"ok"}` |
| Database | Postgres (`estimator` DB, Docker Compose) |
| Embedding model | `text-embedding-3-small` (1536 dimensions) |
| Tools | `curl`, Python `urllib` + `ThreadPoolExecutor` |

---

## 3. Functional API validation

### 3.1 Invalid ingest and search requests (422)

| # | Case | HTTP | Result |
|---|------|------|--------|
| 1 | Empty body `{}` | **422** | Missing `source_path`, `document_type`, `content` |
| 2 | Missing `content` | **422** | Field required |
| 3 | Malformed budget (`budget_id` only) | **422** | Six required `Budget` fields missing |
| 4 | Search with query `"   "` | **422** | `query must not be empty` |
| 5 | Search with `k=0` | **422** | `ge=1` validation |
| 6 | Search with `k=51` | **422** | `le=50` validation |
| 14 | `estimated_hours: "not-a-number"` | **422** | Integer parsing error on component |

### 3.2 Valid ingest and database persistence

**Unique document ingested:**

- `source_path`: `data/budgets/api-manual-test-20260609154359.json`
- Budget: `BUD-API-TEST-001`, component `ZQMS-001` ("Zorblox quantum mesh synthesizer… xyzzy-plugh-42069")

**Response (200):**

```json
{
  "document_id": 16,
  "chunks_created": 1,
  "embedding_dimension": 1536,
  "ingestion_time_ms": 1223
}
```

**Postgres verification:**

```sql
SELECT d.id, d.source_path, COUNT(c.id) AS chunks
FROM documents d
LEFT JOIN chunks c ON c.document_id = d.id
WHERE d.source_path LIKE 'data/budgets/api-manual-test%'
GROUP BY d.id, d.source_path
ORDER BY d.id;
```

| document_id | source_path | chunks |
|---------------|-------------|--------|
| 16 | `api-manual-test-20260609154359.json` | 1 (chunk_id=26, embedding present) |
| 17 | `api-manual-test-zero-20260609154359.json` | 0 |

The response exposes metadata only (no raw vectors), matching the API contract.

### 3.3 Duplicate ingest — sequential (409)

Re-posting the same `source_path` after a successful ingest:

```json
{
  "detail": "Document already ingested",
  "document_id": 16
}
```

HTTP **409** — embedder is not called again.

### 3.4 Directed search — find ingested content

**Query:** `"Zorblox quantum mesh synthesizer xyzzy-plugh-42069"`

| Field | Value |
|-------|-------|
| HTTP | 200 |
| Top-1 `document_id` | **16** (ingested document) |
| Top-1 `budget_id` | **BUD-API-TEST-001** |
| Top-1 `component_id` | **ZQMS-001** |
| Top-1 `distance` | **0.3244** |

The newly inserted chunk ranks first with a low cosine distance.

### 3.5 Unrelated search — new document absent from top-k

**Query:** `"medieval tapestry restoration and Renaissance fresco conservation techniques"`

| Metric | Value |
|--------|-------|
| HTTP | 200 |
| Results returned | 5 (corpus already populated) |
| Distances | 0.79 – 0.82 (high) |
| `BUD-API-TEST-001` in top-5 | **No** |

With a populated corpus, search never returns an empty list; however, the newly ingested document does not appear in the top-5 for an unrelated query.

**Distance contrast:**

| Query | Top-1 distance | Top-1 budget |
|-------|----------------|--------------|
| "Zorblox quantum mesh synthesizer" | **0.3261** | BUD-API-TEST-001 |
| "knitting patterns for wool sweaters" | **0.8779** | BUD-2024-056 |

### 3.6 Additional scenarios

| # | Case | Result |
|---|------|--------|
| 11 | Budget with zero components | **200**, `chunks_created=0`, `ingestion_time_ms=3` (embedder skipped) |
| 15 | Search for zero-chunk document (id=17) | Document 17 **not present** in top-10 results |
| 16 | OAuth query on existing corpus | Top-1 `BUD-2024-014` / `AUTH-001`, distance **0.3884** |
| 17 | Re-ingest same path (sequential) | **409** (not 200) |

### 3.7 Functional validation summary

| Flow | Status |
|------|--------|
| Reject invalid input | OK |
| Ingest + DB persistence | OK |
| Sequential duplicate → 409 | OK |
| Search finds ingested content | OK |
| Unrelated search excludes new doc from top-k | OK |
| Zero-component ingest | OK |
| Existing corpus baseline (OAuth) | OK |

---

## 4. Concurrency validation

Concurrency tests used Python `ThreadPoolExecutor` firing parallel HTTP requests against the live API. Each scenario used fresh `source_path` values with timestamp suffixes to avoid collisions with prior runs (except where duplicate race was intentional).

### 4.1 Scenario A — duplicate `source_path` race (10 workers)

**Setup:** 10 concurrent `POST /api/v1/embeddings/ingest` requests with identical payload and `source_path`:

`data/budgets/api-concurrency-dup-20260609154729.json`

| HTTP status | Count |
|-------------|-------|
| 200 | 1 |
| 500 | 9 |
| 409 | 0 |

- Winning request: `document_id=18`, `chunks_created=1`, `ingestion_time_ms=481`
- Losers: `{"detail":"Unable to ingest budget document."}` (generic 500)
- All 9 failures completed in ~560–768 ms (same window as the winner)

**Root cause:** `run_persistent_ingest` uses check-then-insert (`find_document_id_by_source_path` → `insert_document`). Under concurrency, multiple workers pass the duplicate check before any commit. The database `UniqueConstraint("source_path")` (`uq_documents_source_path`) rejects subsequent inserts, raising `IntegrityError` which the router maps to generic **500** instead of **409**.

**Post-race DB state:** exactly **one** row for the path, **one** chunk — no duplicate documents persisted.

**Sequential follow-up:** re-posting the same `source_path` after the race returns **409** as expected:

```json
{"detail":"Document already ingested","document_id":18}
```

**Confirmation run (6 workers, fresh path):** 1×`200`, 5×`500` — same pattern.

### 4.2 Scenario B — distinct `source_path` (8 workers)

8 concurrent ingests, each with a unique `source_path`.

| HTTP status | Count |
|-------------|-------|
| 200 | 8 |
| 500 | 0 |

- `document_id` values: 28, 29, 30, 31, 32, 33, 34, 35 — all unique
- Latency: 337–439 ms per request
- Postgres: 8 documents, 8 chunks (1 each)

No contention when paths differ.

### 4.3 Scenario C — concurrent search (12 workers)

12 parallel `POST /api/v1/search` requests with varied queries.

| HTTP status | Count |
|-------------|-------|
| 200 | 12 |
| 500 | 0 |

Sample top-1 distances under concurrent load:

| Query (preview) | Top-1 distance |
|-----------------|----------------|
| Zorblox quantum mesh synthesizer xyzzy-plugh-42069 | 0.3244 |
| OAuth 2.0 authentication backend JWT fintech | 0.4239 |
| medieval tapestry restoration fresco | 0.8206 |
| knitting patterns wool sweaters | 0.8575 |

Latency: 359–736 ms. No errors or empty failures observed.

### 4.4 Scenario D — mixed ingest + search (5 workers)

5 concurrent tasks: 2× ingest (same `source_path`), 3× search (`"Heliotrope spectral indexer"`).

| Task | HTTP |
|------|------|
| ingest (worker 0) | **200** |
| ingest (worker 1) | **500** |
| search (workers 0–2) | **200** each |

Searches succeed regardless of ingest race. Duplicate ingest race reproduces the A-pattern (1 winner, 1 loser with 500).

**Post-race DB:** `data/budgets/api-concurrency-mix-20260609154729.json` → `document_id=36`, 1 chunk.

### 4.5 Concurrency summary

| Scenario | Expected | Observed | DB integrity |
|----------|----------|----------|--------------|
| Same `source_path` (N concurrent) | 1×200, (N−1)×409 | 1×200, (N−1)×**500** | OK — single row |
| Distinct paths (N concurrent) | N×200 | N×200 | OK |
| N concurrent searches | N×200 | N×200 | N/A (read-only) |
| Mixed ingest + search | ingest 1×200; search N×200 | ingest 1×200, 1×500; search 3×200 | OK |

### 4.6 Fix applied (2026-06-09)

`run_persistent_ingest` now catches `sqlalchemy.exc.IntegrityError`, rolls back, re-queries `document_id` by `source_path`, and raises `DuplicateDocumentError` so the router returns **409**. See §8 for implementation and post-fix verification.

---

## 5. Quality review findings (automated suite)

Prior to manual testing, the fast pytest suite for ingest/search was run:

| Scope | Tests | Result |
|-------|-------|--------|
| Router ingest | 8 | Pass |
| Persistent ingest service | 6 | Pass |
| Router search | 6 | Pass |
| Search service | 2 | Pass |
| Search repository (SQL compile) | 4 | Pass |
| In-memory ingest | 1 | Pass |
| Milestone E2E ingest | 8 | Pass |
| Schemas + query_examples | 26 | Pass |
| **Total** | **61 passed** | 2 deselected (`@pytest.mark.slow`) |

Notable automated gaps confirmed by manual/concurrency testing:

1. No ingest → search integration test against real Postgres.
2. No smoke test for search with live API key + database.
3. Duplicate race returns 500 (confirmed manually in §4.1).
4. `_InMemoryRepository` duplicated across three test modules (maintenance burden).

---

## 6. Test data left in dev database

The following manual and concurrency test artifacts remain in the local dev database:

| Prefix | document_ids (approx.) | Notes |
|--------|----------------------|-------|
| `api-manual-test-*` | 16, 17 | Functional validation |
| `api-concurrency-dup-*` | 18, 38 | Race tests |
| `api-concurrency-dist-*` | 28–35 | Distinct-path concurrency |
| `api-concurrency-mix-*` | 36 | Mixed workload |

Clean up with targeted `DELETE` on `documents` (cascades to `chunks`) or `alembic downgrade base` + re-migrate if a full reset is acceptable.

---

## 7. How to reproduce

### Functional checks

```bash
# Health
curl -sS http://127.0.0.1:8000/health

# Ingest (replace content with valid Budget JSON)
curl -sS -X POST http://127.0.0.1:8000/api/v1/embeddings/ingest \
  -H 'Content-Type: application/json' \
  -d @payload.json

# Search
curl -sS -X POST http://127.0.0.1:8000/api/v1/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"OAuth authentication backend","k":5}'
```

### Automated suite (offline, mocked)

```bash
uv run pytest tests/embedding_pipeline/test_router.py \
  tests/embedding_pipeline/test_persistent_ingest_service.py \
  tests/embedding_pipeline/test_search_router.py \
  tests/embedding_pipeline/test_search_service.py \
  tests/embedding_pipeline/test_search_repository.py \
  tests/embedding_pipeline/test_milestone_e2e.py -v
```

### Concurrency duplicate race (illustrative)

Fire N parallel POST requests with the same `source_path` using `ThreadPoolExecutor` or `xargs -P`. Expect 1×200 and (N−1)×500 with current implementation; sequential re-post should return 409.

### Post-index verification (feature-040)

After `uv run alembic upgrade head`, confirm HNSW index and observability metrics:

```bash
export DATABASE_URL=postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator
uv run alembic upgrade head

docker compose exec -T postgres psql -U estimator -d estimator -c \
  "SELECT indexname, indexdef FROM pg_indexes WHERE indexname = 'ix_chunks_embedding_hnsw';"

docker compose exec -T postgres psql -U estimator -d estimator < scripts/pgvector_observability.sql
```

Diagnostic `EXPLAIN` (expect `Index Scan using ix_chunks_embedding_hnsw` when `enable_seqscan` is off on small corpora):

```sql
ANALYZE chunks;
SET enable_seqscan = off;
EXPLAIN SELECT id FROM chunks
WHERE embedding IS NOT NULL
ORDER BY embedding <=> (SELECT embedding FROM chunks WHERE embedding IS NOT NULL LIMIT 1)
LIMIT 5;
```

After sustained `POST /api/v1/search` traffic, `idx_scan` on `ix_chunks_embedding_hnsw` in the observability script should be ≥ 1.

---

## 8. Fix: concurrent duplicate ingest → 409

**Problem (pre-fix):** check-then-insert race caused `IntegrityError` on `uq_documents_source_path`, surfaced as generic **500**.

**Change:** `app/embedding_pipeline/persistent_ingest.py` catches `IntegrityError` after rollback, re-reads `document_id` by `source_path`, and raises `DuplicateDocumentError` when the row exists.

**Test:** `test_run_persistent_ingest_integrity_error_maps_to_duplicate` in `tests/embedding_pipeline/test_persistent_ingest_service.py`.

**Post-fix live verification (2026-06-09, local `uvicorn` on `:8001`):** 10 concurrent ingests with the same `source_path` → **1×200**, **9×409**, single `document_id=54`. Pre-fix Docker `:8000` image still returned 500 until rebuilt/restarted with the new code.

---

**Last updated:** 2026-06-09  
**Status:** Manual validation complete; concurrent duplicate race fixed.
