# Feature: Indexed Lexical Path — `content_tsv` + GIN + `pg_trgm` (Optional)

> Sub-feature 7 of 7 of the epic `feature-041-retrieval-debug-observability-screen`. **Optional / performance.**
> Depends on: `feature-043` (lexical full-text branch baseline). Can land any time after 043.
> Internal tooling. Not user-facing.

## Why this sub-feature

`feature-043` deliberately ships lexical search as an on-the-fly `to_tsvector` sequential scan — a teaching baseline consistent with features 038/040. That does not scale and recomputes the `tsvector` on every query. This sub-feature replaces the baseline with an indexed lexical path and adds `pg_trgm` for exact technical-token matching (acronyms, versions, codes), mirroring how feature-040 added HNSW for the vector path. It is a pure optimization with no API contract change.

## Objective

Add an Alembic migration creating a generated `content_tsv` column with a GIN index on `chunks`, enable the `pg_trgm` extension (and a trigram index for exact-token similarity), and switch `LexicalSearchRepository` to use the indexed column while keeping the lexical branch's response contract identical.

## Value increment (what ships and why it matters)

- Lexical queries use a precomputed, indexed `tsvector` (GIN) instead of per-query `to_tsvector`, with `pg_trgm` enabling robust exact-token matching.
- Faster, scalable lexical retrieval; query-plan evidence (`EXPLAIN`) shows index usage.
- Result: the lexical branch graduates from baseline to production-oriented, with no change to the debug API or UI.

## SMART framing

- **Specific:** one migration (`0003`) + repository swap to indexed path; no contract change.
- **Measurable:** AC-01…AC-10; `EXPLAIN` shows GIN/trigram usage; lexical results unchanged in shape.
- **Achievable:** standard pgvector-adjacent Postgres FTS + `pg_trgm`; mirrors feature-040 migration pattern.
- **Relevant:** removes the known lexical scaling limitation.
- **Time-boxed:** Size S, ~5 baby steps.

## Context

- Only migrations `0001` (schema) and `0002` (HNSW) exist; Alembic is the source of truth for index DDL (same pattern used for the GIN metadata index and HNSW).
- `feature-043` lexical SQL uses `to_tsvector('english', content)` + `websearch_to_tsquery` + `ts_rank_cd`.
- Static migration tests live in `tests/test_alembic_migration.py` (assert DDL contents).

## Scope

### Includes

- Alembic migration `0003_add_chunks_content_tsv_and_trgm.py` (`down_revision = "0002"`):
  - add generated column `content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED`.
  - GIN index `ix_chunks_content_tsv_gin` on `content_tsv`.
  - `CREATE EXTENSION IF NOT EXISTS pg_trgm`.
  - GIN trigram index `ix_chunks_content_trgm` on `content` (`gin_trgm_ops`) for exact-token/`ILIKE` similarity.
  - `downgrade()` drops indexes + column (extension optionally retained; documented).
- Switch `LexicalSearchRepository` to query `content_tsv @@ websearch_to_tsquery(...)` with `ts_rank_cd(content_tsv, ...)`; optionally blend trigram similarity for exact tokens (documented), keeping the response identical.
- Extend static Alembic tests for `0003`; lexical repository regression tests (shape unchanged).
- Docs sweep mirroring feature-040 style (technical README, README rationale, architecture HTML, Second Brain).

### Excludes

- API/UI changes (lexical branch contract from 043 is preserved).
- BM25 / external search engines.
- Changing vector/HNSW config or embedding model.
- `CREATE INDEX CONCURRENTLY` (transactional Alembic acceptable for course corpus; production note documented).

## Functional Requirements

### FR-01 — Migration

After `uv run alembic upgrade head`: `chunks.content_tsv` exists as a stored generated column; `ix_chunks_content_tsv_gin` (GIN) and `ix_chunks_content_trgm` (GIN `gin_trgm_ops`) exist; `pg_trgm` extension is enabled.

### FR-02 — Indexed lexical query

`LexicalSearchRepository` ranks via `ts_rank_cd(content_tsv, websearch_to_tsquery('english', :q))` filtered by `content_tsv @@ ...`, ordered desc, limited by `top_k`. Response fields (`chunk_id`, `document_id`, `chunk_type`, `content`, `metadata`, `ts_rank`, `matched_terms`) are unchanged from `feature-043`.

### FR-03 — Plan evidence & downgrade

`EXPLAIN` on the lexical query shows GIN index usage on a populated corpus (document the command). `alembic downgrade 0002` removes the column/indexes and leaves the lexical baseline behavior intact (repository must tolerate both states, or the swap is gated — document the chosen approach).

## Acceptance Criteria

- [ ] AC-01: `0003_add_chunks_content_tsv_and_trgm.py` exists with `down_revision = "0002"`.
- [ ] AC-02: Upgrade creates `content_tsv` generated column + `ix_chunks_content_tsv_gin`.
- [ ] AC-03: `pg_trgm` enabled + `ix_chunks_content_trgm` (`gin_trgm_ops`) created.
- [ ] AC-04: `LexicalSearchRepository` uses `content_tsv`; lexical response shape is unchanged from `feature-043`.
- [ ] AC-05: `EXPLAIN` shows GIN index usage on the lexical query with a populated corpus.
- [ ] AC-06: `alembic downgrade 0002` drops the new column/indexes; baseline lexical behavior remains valid.
- [ ] AC-07: Static Alembic tests assert `0003` DDL (column, both indexes, extension).
- [ ] AC-08: Lexical repository regression tests pass (shape unchanged, mocked session).
- [ ] AC-09: Default suite passes offline; no real keys/live DB required.
- [ ] AC-10: Technical docs, README, architecture HTML, and a Second Brain note record the indexed lexical path and `EXPLAIN` evidence.

## Test Plan

- Static: `tests/test_alembic_migration.py` — `0003` contents (column, GIN, trigram, extension).
- Repository: indexed lexical statement shape + mapping (mocked session); response unchanged vs 043.
- Manual: Compose Postgres — upgrade, `\d chunks`, `EXPLAIN` lexical query (GIN), curl debug `strategies: ["lexical"]` (same shape), downgrade/upgrade round-trip.

## Verification

- Automated: `uv run pytest tests/test_alembic_migration.py tests/embedding_pipeline -q`.
- Manual: migration up/down + `EXPLAIN` + lexical curl on Compose Postgres.
- Not verified yet: large-corpus latency benchmarks; `CREATE INDEX CONCURRENTLY` at scale.

## Documentation Plan

- `docs/technical/README.md`: indexed lexical path, `content_tsv`, GIN, `pg_trgm`, `EXPLAIN` command (mirror feature-040 §).
- `README.md`: update lexical rationale (baseline → indexed) + verification commands.
- `docs/arquitectura-estimador-cag.html`: lexical index node/footnote.
- Second Brain: `learnings/docs/sesiones/...` note with before/after plan evidence.

## Implementation Plan

- [ ] Step 1: Add migration `0003` (column + GIN + `pg_trgm` + trigram index; upgrade/downgrade).
- [ ] Step 2: Extend `tests/test_alembic_migration.py` static checks (RED→GREEN).
- [ ] Step 3: Switch `LexicalSearchRepository` to `content_tsv` (shape unchanged) + repository tests.
- [ ] Step 4: Manual migration + `EXPLAIN` + lexical curl verification on Compose.
- [ ] Step 5: Docs sweep (technical, README, architecture, Second Brain).

## Estimation

- Size: S
- Estimated time: 2 hours
- Planned steps: 5
- Depends on: `feature-043-lexical-fulltext-search-branch`
- Contract impact: no API/UI response contract change.

## Implementation progress

- [ ] Step 1: Add static migration coverage for indexed lexical DDL.
- [ ] Step 2: Add migration `0003` for `content_tsv`, GIN, and `pg_trgm`.
- [ ] Step 3: Switch lexical repository SQL to the indexed `content_tsv` path.
- [ ] Step 4: Document indexed lexical verification and architecture impact.
- [ ] Step 5: Final verification, handoff, commit table, and PR closure readiness.

## Pull request

- PR: https://github.com/povedica/master-ia-lidr/pull/44 (draft, WIP)
- Branch: `feature/048-indexed-lexical-tsvector-migration`
