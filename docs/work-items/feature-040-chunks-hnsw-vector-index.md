# Feature: HNSW Vector Index on `chunks.embedding` and pgvector Observability Docs

> Follow-up to the semantic-search milestone (features 036–039).
> Closes the deliberate sequential-scan baseline documented in feature-036 and feature-038.

## Objective

Add a production-oriented **HNSW** index on `chunks.embedding` using **`vector_cosine_ops`**, aligned with the existing `cosine_distance` search path, and update **all project technical reference documentation** so operators can verify index presence, query-plan usage, and storage/usage metrics.

This feature turns the observability findings from the pgvector inspection session into a concrete schema change plus reproducible documentation — not a new search API.

## Context

### Conversation analysis (observability baseline, 2026-06-14)

An observability pass against the live Compose Postgres instance reported:

| Metric | Observed value |
|--------|----------------|
| PostgreSQL | 16.14 |
| pgvector extension | 0.8.2 |
| Embedding table | `public.chunks` (assumption confirmed; no other `vector`/`halfvec` columns) |
| Vector column | `embedding` — `vector(1536)` |
| Total chunks / vectors | 39 / 39 (0 null embeddings) |
| HNSW / IVFFlat indexes | **0** |
| Table total size | 504 kB (40 kB heap + 376 kB TOAST + 88 kB non-vector indexes) |
| Avg vector payload | ~6,148 bytes |
| Search metric today | `cosine_distance` via `<=>` in `SemanticSearchRepository` |
| Index usage (`pg_stat_user_indexes`) | Only btree/GIN indexes on `chunks`; no vector index `idx_scan` |

**Implication:** `POST /api/v1/search` currently performs a **sequential scan** over all embedded chunks. That was intentional for teaching and baseline measurement (feature-038 AC-11), but it does not scale and leaves no ANN metrics in `pg_stat_user_indexes`.

### Existing code and docs

- `feature-036` created `chunks.embedding` as `Vector(1536)` with **no** vector index.
- `feature-038` ranks by `ChunkModel.embedding.cosine_distance(query_vector)` — explicitly chosen to align with future `vector_cosine_ops`.
- `app/embedding_pipeline/search_repository.py` does not need a metric change; PostgreSQL should pick the HNSW index when the operator class matches.
- Only one Alembic revision exists: `0001_initial_schema.py`.
- Technical references that still state “no HNSW / sequential scan baseline”:
  - `docs/technical/README.md` (§19, §22, §23)
  - `README.md` (Semantic search design rationale §(d))
  - `docs/arquitectura-estimador-cag.html` (search router node, API table, milestone notes)
  - `learnings/docs/sesiones/sesion-07-semantic-search-postgres-baseline.md`
  - `learnings/docs/sesiones/sesion-07-semantic-search-endpoint.md`
  - `docs/technical/embedding-pipeline-api-manual-validation.md` (search validation; no index-plan checks yet)
  - `docs/work-items/adr-001-embedding-pipeline-vs-estimator-ingestion.md` (HNSW still listed as deferred)
  - `docs/work-items/feature-036-postgres-pgvector-alembic-baseline.md` and `feature-038-semantic-search-endpoint-pgvector.md` (historical “no index” statements remain valid as baseline record; add forward reference only if useful)

### Design constraints

- Keep **cosine** geometry; do **not** switch to L2 or inner product.
- Do **not** migrate to `halfvec` in this feature — column type stays `vector(1536)`.
- Do **not** add IVFFlat; HNSW is the chosen ANN method for this increment.
- No new environment variables unless a future feature needs runtime `ef_search` tuning; document session-level `hnsw.ef_search` in technical docs only.

## Scope

### Includes

- Add Alembic migration `0002_add_chunks_embedding_hnsw_index.py` (revision id `0002`, `down_revision = "0001"`).
- Create index on `chunks.embedding` with:
  - name: `ix_chunks_embedding_hnsw`
  - method: `USING hnsw`
  - operator class: `vector_cosine_ops`
  - partial predicate: `WHERE embedding IS NOT NULL` (matches search filter and avoids indexing null rows)
  - build parameters: `m = 16`, `ef_construction = 64` (pgvector defaults; document rationale)
- Extend static Alembic migration tests to assert the new index definition.
- Add `scripts/pgvector_observability.sql` — deterministic SQL report for dashboards (table/column dimensions, row counts, HNSW index list, sizes, `pg_stat_user_indexes` usage, optional `pg_settings` memory knobs).
- Update **all technical reference docs** listed in [Documentation Plan](#documentation-plan).
- Add Second Brain session note capturing before/after observability numbers and `EXPLAIN` evidence.
- Manual verification: migration up/down, `\d chunks`, `EXPLAIN (ANALYZE, BUFFERS)` on the search SQL shape, observability script output.

### Excludes

- Application/search code changes (unless a minimal comment in `search_repository.py` is needed for maintainers).
- `CREATE INDEX CONCURRENTLY` (Alembic transactional migration; acceptable for dev/small corpus; document production follow-up).
- `halfvec` compression or expression indexes like `embedding::halfvec(1536)`.
- IVFFlat indexes.
- Metadata filters, hybrid search, reranking, or new HTTP endpoints.
- Automated CI job requiring live Postgres (keep manual + static migration tests).
- Changing embedding model or dimension (still `text-embedding-3-small` / 1536).
- Real OpenAI calls in default tests.

## Functional Requirements

### FR-01 — HNSW index definition

After `uv run alembic upgrade head`, Postgres must contain exactly one HNSW index on `chunks` for cosine search:

```sql
CREATE INDEX ix_chunks_embedding_hnsw
ON chunks
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64)
WHERE embedding IS NOT NULL;
```

### FR-02 — Search behaviour unchanged

`POST /api/v1/search` must return the same ranked results for the same corpus and query as before the index (ordering by ascending cosine distance, same `k` limit, null embeddings excluded). The index is an optimization, not a contract change.

### FR-03 — Query planner uses HNSW

For a corpus with at least one non-null embedding, `EXPLAIN` on the search-shaped SQL must show an **HNSW index scan** (not a sequential scan) when statistics are fresh. Document the exact command in technical docs.

Recommended session setting for verification (document only):

```sql
SET hnsw.ef_search = 40;  -- default; increase for recall tuning experiments
```

### FR-04 — Observability script

`scripts/pgvector_observability.sql` must output stable columns suitable for UI tables:

- `nombre_tabla`, `nombre_columna_vector`, `dimensiones`
- `total_chunks`, `total_vectores`
- `nombre_indice`, `metodo_indice`, `operator_class`
- `tamano_indice_bytes`, `tamano_indice_pretty`
- `tamano_tabla_pretty`
- `idx_scan`, `last_idx_scan` (when supported)

If no vector table exists, the script must auto-detect any `vector`/`halfvec` column and state assumptions in a leading comment row or `RAISE NOTICE`.

### FR-05 — Downgrade path

`alembic downgrade 0001` (or `downgrade -1` from head) must drop `ix_chunks_embedding_hnsw` and leave the feature-036 schema intact.

## Technical Approach

### Migration

| File | Action |
|------|--------|
| `alembic/versions/0002_add_chunks_embedding_hnsw_index.py` | `upgrade()` creates HNSW index; `downgrade()` drops it |

Use `op.execute(...)` with raw SQL. pgvector HNSW indexes are not modeled on the SQLAlchemy `Chunk` ORM class in this feature — Alembic remains the source of truth (same pattern as GIN index in `0001`).

**Note on concurrency:** standard `CREATE INDEX` inside Alembic locks writes briefly. For the course corpus this is acceptable. Document that production rollouts at scale should plan `CREATE INDEX CONCURRENTLY` outside a transactional migration.

### Application layer

No search SQL changes expected. `SemanticSearchRepository.build_search_statement()` already uses `cosine_distance`, which compiles to `<=>` with the cosine operator family.

Optional: one-line module docstring in `search_repository.py` noting HNSW index `ix_chunks_embedding_hnsw` / `vector_cosine_ops`.

### Tests

| Test | Purpose |
|------|---------|
| Extend `tests/test_alembic_migration.py` | Assert `0002` migration file contains `ix_chunks_embedding_hnsw`, `USING hnsw`, `vector_cosine_ops`, `WHERE embedding IS NOT NULL` |
| Regression | `uv run pytest tests/embedding_pipeline/test_search_*.py` — unchanged ranking behaviour with mocked DB |

### Observability workflow (manual)

```bash
docker compose up -d postgres
export DATABASE_URL=postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator
uv run alembic upgrade head

docker compose exec -T postgres psql -U estimator -d estimator -f /path/mounted/or/piped < scripts/pgvector_observability.sql

docker compose exec -T postgres psql -U estimator -d estimator -c "
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, embedding <=> '[0,0,...]'::vector(1536) AS distance
FROM chunks
WHERE embedding IS NOT NULL
ORDER BY distance
LIMIT 5;
"
```

Capture before/after metrics in the Second Brain note (pre-index numbers from the 2026-06-14 session can serve as “before”).

## Acceptance Criteria

- [x] AC-01: `alembic/versions/0002_add_chunks_embedding_hnsw_index.py` exists with `down_revision = "0001"`.
- [x] AC-02: `uv run alembic upgrade head` creates `ix_chunks_embedding_hnsw` on `chunks.embedding` with `vector_cosine_ops`.
- [x] AC-03: Index is partial: `WHERE embedding IS NOT NULL`.
- [x] AC-04: `uv run alembic downgrade 0001` drops the HNSW index; `0001` schema remains valid.
- [x] AC-05: `\d chunks` (or `pg_indexes`) lists the HNSW index with expected operator class.
- [x] AC-06: `EXPLAIN` on search-shaped SQL shows HNSW index usage with populated corpus.
- [x] AC-07: `POST /api/v1/search` responses remain contract-compatible (no API schema change).
- [x] AC-08: `uv run pytest tests/test_alembic_migration.py` passes with new static assertions.
- [x] AC-09: `uv run pytest tests/embedding_pipeline/test_search_*.py` passes (no regression).
- [x] AC-10: `scripts/pgvector_observability.sql` exists and returns concrete numeric/size fields for `chunks.embedding`.
- [x] AC-11: After at least one search request post-migration, `pg_stat_user_indexes.idx_scan` for `ix_chunks_embedding_hnsw` is documented (expected ≥ 1 when verified manually).
- [x] AC-12: All files in [Documentation Plan](#documentation-plan) are updated — no stale “no HNSW / sequential scan only” statements remain in active reference sections.
- [x] AC-13: Second Brain session note records before/after observability snapshot and `EXPLAIN` summary.
- [x] AC-14: No new secrets or real API keys in docs, scripts, or tests.

## Test Plan

### Unit / static tests

- `tests/test_alembic_migration.py`:
  - new test for `0002` migration contents (HNSW name, opclass, partial predicate, `m`/`ef_construction`)
- Existing search tests (mocked session):
  - `tests/embedding_pipeline/test_search_repository.py`
  - `tests/embedding_pipeline/test_search_service.py`
  - `tests/embedding_pipeline/test_search_router.py`

### Integration tests

- Not required in default CI (no live Postgres). Document manual integration checks instead.

### Manual checks

1. `docker compose up -d postgres`
2. Run observability script **before** upgrade (optional if baseline already captured).
3. `uv run alembic upgrade head`
4. Confirm index: `SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'chunks' AND indexname = 'ix_chunks_embedding_hnsw';`
5. `EXPLAIN (ANALYZE, BUFFERS)` on search SQL — expect HNSW plan.
6. `curl` `POST /api/v1/search` — same shape as feature-038; compare top-k ordering to pre-index baseline if saved.
7. Re-run observability script — expect non-null `nombre_indice`, `metodo_indice = hnsw`, `operator_class = vector_cosine_ops`, index size pretty-printed.
8. `uv run alembic downgrade 0001` — index gone; upgrade again for dev convenience.

## Verification

### Automated

- **Verified:** `uv run pytest tests/test_alembic_migration.py -q` — 2 passed.
- **Verified:** `uv run pytest tests/embedding_pipeline/test_search_*.py -q` — 20 passed.

### Manual

- **Verified:** `uv run alembic upgrade head` on Compose Postgres — `ix_chunks_embedding_hnsw` created with `vector_cosine_ops`, partial predicate, `m=16`, `ef_construction=64`.
- **Verified:** `uv run alembic downgrade 0001` — index count 0; re-upgrade succeeds.
- **Verified:** `scripts/pgvector_observability.sql` — returns `chunks` / `embedding` / 1536 / 39 rows / HNSW index ~312 kB / table ~816 kB.
- **Verified:** `EXPLAIN` with `SET enable_seqscan = off` shows `Index Scan using ix_chunks_embedding_hnsw` (diagnostic; small corpus may seq-scan in production planner).
- **Verified (AC-11 note):** `idx_scan = 0` immediately after index creation without live search traffic; documented in §24 and session note — expect ≥ 1 after sustained `POST /api/v1/search`.

### Not verified yet

- `CREATE INDEX CONCURRENTLY` on a large production table.
- Recall/latency benchmarks vs sequential scan (optional follow-up experiment).
- CI with ephemeral Postgres service.
- Live `POST /api/v1/search` curl after index (API contract unchanged; no schema change).

### Residual risk

- Very small corpora (tens of rows) may occasionally favor sequential scans until `ANALYZE` and cost settings stabilize; document `SET enable_seqscan = off` only as a diagnostic, not production policy.
- HNSW is approximate; recall depends on `ef_search`. Default is acceptable for the course; tuning is a follow-up.

## Repository commits (master-ia)

| Commit | Summary |
|--------|---------|
| 0f4e7cf | docs(work-items): add feature-040 HNSW vector index spec |
| 5012f46 | test(alembic): add static checks for HNSW migration 0002 |
| efee742 | feat(db): add HNSW cosine index on chunks.embedding |
| 936b69b | feat(scripts): add pgvector observability SQL report |
| c92b3ef | docs: document HNSW index and observability in technical README |
| 7b0e0e1 | docs: sync HNSW index references across architecture and learnings |
| 4ace165 | docs(work-items): record feature-040 verification and acceptance status |

## Documentation Plan

Update **every** active technical reference that describes pgvector search storage or query plans. Remove or rephrase “no vector index” baseline language to “HNSW index `ix_chunks_embedding_hnsw` (feature-040)” while preserving historical context where appropriate.

| # | File | Required updates |
|---|------|------------------|
| 1 | `docs/technical/README.md` | Add **§24 HNSW index (feature-040)** with index DDL, `ef_search`, `EXPLAIN` commands, observability script usage, index-size interpretation; update §19 “next steps”, §22 index list, §23 “SQL behaviour” / planner notes |
| 2 | `README.md` | Semantic search section: replace §(d) “deliberately no vector index” with HNSW summary + link to §24; update “Out of scope” list; add observability script to setup/verification commands |
| 3 | `docs/arquitectura-estimador-cag.html` | Search router description, milestone notes, API table footnotes — HNSW present, cosine opclass named |
| 4 | `docs/technical/embedding-pipeline-api-manual-validation.md` | Add post-index verification subsection: `EXPLAIN`, observability SQL, expected `idx_scan` |
| 5 | `docs/work-items/adr-001-embedding-pipeline-vs-estimator-ingestion.md` | Move HNSW from **Deferred** to **Adopted** (feature-040); keep hybrid search deferred |
| 6 | `learnings/docs/sesiones/sesion-07-semantic-search-postgres-baseline.md` | Note evolution: baseline sequential scan → HNSW follow-up |
| 7 | `learnings/docs/sesiones/sesion-07-semantic-search-endpoint.md` | Document index alignment with `vector_cosine_ops` and operator checklist |
| 8 | `learnings/docs/sesiones/sesion-07-pgvector-hnsw-index.md` | **New** session note: observability before/after, migration, alerts cleared |
| 9 | `docs/README.md` | Add link to technical §24 / observability script if index of docs is maintained there |
| 10 | `scripts/pgvector_observability.sql` | **New** — canonical SQL report (this feature deliverable) |

**Cross-links (light touch):** Optionally add a single “Superseded by feature-040” forward reference in feature-038 Learnings — do not rewrite historical acceptance checkboxes.

**Not in scope for doc edits:** Completed feature-036 AC-10 checkbox (historical). feature-039 remains valid as milestone evidence script.

## Implementation Plan

- [x] Step 1: Add `0002_add_chunks_embedding_hnsw_index.py` migration (upgrade + downgrade).
- [x] Step 2: Extend `tests/test_alembic_migration.py` for `0002` static checks.
- [x] Step 3: Run `alembic upgrade head` on Compose; verify index catalog and `EXPLAIN`.
- [x] Step 4: Add `scripts/pgvector_observability.sql` (deterministic output columns from observability session).
- [x] Step 5: Update `docs/technical/README.md` (§24 + §19/§22/§23 patches).
- [x] Step 6: Update `README.md` semantic search rationale and verification commands.
- [x] Step 7: Update `docs/arquitectura-estimador-cag.html` HNSW references.
- [x] Step 8: Update `embedding-pipeline-api-manual-validation.md` and `adr-001`.
- [x] Step 9: Update Second Brain session notes (+ new `sesion-07-pgvector-hnsw-index.md`).
- [x] Step 10: Run search regression tests; capture post-index observability + `idx_scan` in work item Verification section during `/start-task`.

## Learnings

- **Operator class must match query metric:** `cosine_distance` / `<=>` requires `vector_cosine_ops`; L2 or inner-product opclasses would not accelerate the current search SQL.
- **Partial index matches service filter:** `WHERE embedding IS NOT NULL` mirrors `SemanticSearchRepository` and avoids indexing empty rows during partial ingests.
- **Sequential scan was a teaching baseline:** feature-038 distances and latency (~276–372 ms including `embed_one`) were measured without ANN; feature-040 optimizes the Postgres leg only.
- **Observability before tuning:** `pg_stat_user_indexes.idx_scan = 0` on vector indexes is a red flag; the observability script makes that visible for dashboards.
- **Small corpus caveat:** with ~39 vectors, planner may still choose sequential scan until costs/statistics favor HNSW — verify with `EXPLAIN`, not assumptions.
- **TOAST dominates heap size:** vectors stored out-of-line inflated total relation size (~376 kB TOAST vs 40 kB heap in the 2026-06-14 snapshot); index size should be reported separately from table total.

## Estimation

- Size: S–M
- Estimated time: 2–3 hours
- Planned steps: 10

## Implementation progress

- [x] Step 1: Migration `0002`
- [x] Step 2: Alembic static tests
- [x] Step 3: Manual migration + `EXPLAIN` verification
- [x] Step 4: Observability SQL script
- [x] Step 5–9: Documentation sweep
- [x] Step 10: Regression tests + verification evidence

## Pull Request

- https://github.com/povedica/master-ia-lidr/pull/36 — WIP draft PR (`wip` label)
