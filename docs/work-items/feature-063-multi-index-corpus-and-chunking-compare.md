# Feature: Multi-Index Corpus and Chunking Compare (Phase 3 parity)

## Objective

Grow the retrieval corpus beyond budget JSON and expose a **chunking lab** API:

1. Add a `collection` discriminator on `chunks` (single-table multi-index — ADR-001 friendly).
2. Transcript + technical-doc parsers and ingest path (CLI first, optional HTTP).
3. Real collection routing in `retrieval_router` (replace feature-061 stub).
4. `POST /api/v1/embeddings/compare` — compare ≥3 chunking strategies on sample budgets; return stats + optional retrieval preview.

This is **Phase 3 parity** child slice **Step 9** of `docs/work-items/feature-053-official-master-parity-alignment.md`.

## Context

### Official reference

| Artifact | Official path | Behavior |
| --- | --- | --- |
| Collections | `retrieval/collections.py` | budgets / transcripts / technical_docs registry |
| Transcript parser | `ingestion/parsers/transcript_txt.py` | Meeting segments → chunks |
| Compare API | `api/embeddings.py` `/compare` | Multi-strategy chunk stats + query preview |
| Chunking strategies | `chunking/strategies/*` | structural, recursive, sentence-window, … |

### `master-ia` fork choices

- **Prefer `collection` column** on existing `chunks` + `documents.document_type` over three separate tables (feature-053 learning #4).
- Collection values: `budgets`, `transcripts`, `technical_docs` (plural, matching feature-061 stub label `budgets`).
- Reuse `embedding_pipeline/` for parsers, chunkers, ingest orchestration (ADR-001 layering).
- Chunking compare: port **subset** of strategies useful for teaching — at minimum `structural` (existing), `recursive`, `sentence_window` (add `langchain-text-splitters` as optional dev dep if needed).
- Compare endpoint is **non-persistent** (no DB writes).
- Auth: reuse embeddings/ingest key pattern or open in dev when keys unset.

### Parent roadmap

- Depends on: `feature-061` (`advanced_retrieve`, `retrieval_router` stub).
- Blocks: transcript-heavy RAG eval, advanced routing accuracy.
- Parallel with: none until `feature-062` merges (optional overlap on retrieve stage only).

## Scope

### Includes

- Alembic `0005_add_chunks_collection.py`: `collection VARCHAR NOT NULL DEFAULT 'budgets'`, index `(collection, chunk_type)`.
- Backfill existing rows to `collection='budgets'`.
- `app/embedding_pipeline/collections.py` — registry + `match_rules()` port (simplified).
- Update `retrieval_router.route_collection()` to use rule patterns.
- Filter `advanced_retrieve` / repositories by `collection` when routing enabled.
- Parsers: `transcript_txt.py`, `technical_doc_md.py` (or txt) under `embedding_pipeline/parsers/`.
- CLI: `app/scripts/ingest_transcript.py` (and technical doc variant) writing to Postgres.
- Fixtures under `tests/fixtures/` for ingest + retrieval integration.
- `POST /api/v1/embeddings/compare` + schemas.
- Extend `eval_retrieval` with named `StageConfig` presets note (mapping doc only if code touch is small).
- `.env.example`, README, technical docs.

### Excludes

- Corpus index async jobs (202 + poll) — FR-18 deferred.
- Full 7 official chunking strategies.
- Presidio PII (`feature-065`).
- Rails chunking lab UI.
- IVFFlat / halfvec tuning.

## Functional Requirements

- **FR-01:** Migration adds `collection` with default `budgets`; existing ingest unchanged.
- **FR-02:** Transcript fixture ingests → searchable with `collection='transcripts'` filter.
- **FR-03:** Technical doc fixture ingests → searchable with `collection='technical_docs'`.
- **FR-04:** `route_collection()` returns matching collection(s) for rule patterns (unit tested).
- **FR-05:** `POST /api/v1/retrieval/advanced` returns correct `collection` provenance per row (AC-12 regression).
- **FR-06:** Compare endpoint accepts sample budget JSON + strategy list; returns chunk count, avg size, estimated embedding cost per strategy.
- **FR-07:** Compare with queries returns top-k chunk previews per strategy (no persist).
- **FR-08:** Unknown strategy name → 400.
- **FR-09:** Layering: parsers/chunkers in `embedding_pipeline`; routers thin.

## Technical Approach

### Migration

```sql
ALTER TABLE chunks ADD COLUMN collection VARCHAR(64) NOT NULL DEFAULT 'budgets';
CREATE INDEX ix_chunks_collection_chunk_type ON chunks (collection, chunk_type);
```

### Module layout

```text
alembic/versions/0005_add_chunks_collection.py
app/embedding_pipeline/collections.py
app/embedding_pipeline/parsers/transcript_txt.py
app/embedding_pipeline/parsers/technical_doc.py
app/embedding_pipeline/chunking_compare.py
app/routers/embeddings_compare.py          # or extend embeddings.py
app/schemas/embeddings_compare.py
app/embedding_pipeline/retrieval_router.py # replace stub
tests/embedding_pipeline/test_collections.py
tests/test_embeddings_compare_endpoint.py
tests/embedding_pipeline/test_transcript_ingest.py
```

### Chunking compare (MVP)

- Input: list of budget JSON objects (same shape as ingest), `strategies: list[str]`, optional `queries: list[str]`, `top_k`.
- Output: `stats_per_strategy`, optional `queries_per_strategy`.
- Reuse `OpenAIEmbedder` for query preview only when queries provided.

### Settings preview

```text
RETRIEVAL_ROUTING_ENABLED=true
CHUNKING_COMPARE_DEFAULT_STRATEGIES=structural,recursive,sentence_window
```

## Acceptance Criteria

- [ ] **AC-01:** Migration applies cleanly on empty and populated DB (test container).
- [ ] **AC-02:** Ingest transcript fixture → advanced retrieval finds chunk in `transcripts` (AC-16 from feature-053).
- [ ] **AC-03:** Router routes "meeting transcript" query toward `transcripts` in unit test.
- [ ] **AC-04:** `POST /api/v1/embeddings/compare` returns ≥3 strategy rows for bundled sample (AC-17).
- [ ] **AC-05:** Budget ingest still writes `collection='budgets'`.
- [ ] **AC-06:** `uv run pytest` fast suite passes.
- [ ] **AC-07:** `.env.example` + README updated.

## Test Plan

### Unit tests

- Collection registry + `match_rules`.
- Transcript parser segment boundaries.
- Compare stats deterministic without embedder (structural-only path).

### Integration tests

- Ingest transcript fixture + retrieve with collection filter (SQLite/Postgres test patterns from embedding_pipeline).

### Manual

- `uv run python app/scripts/ingest_transcript.py --help`
- Swagger compare with bundled sample budgets.

## Verification

| Check | Command |
| --- | --- |
| Migration | `uv run alembic upgrade head` (test DB) |
| Collections | `uv run pytest tests/embedding_pipeline/test_collections.py -q` |
| Compare | `uv run pytest tests/test_embeddings_compare_endpoint.py -q` |
| Fast suite | `uv run pytest` |

**Not verified yet:** cross-collection fusion quality vs official scoreboard.

## Documentation Plan

| Artifact | Update |
| --- | --- |
| `.env.example` | Routing + compare defaults |
| `README.md` | Multi-index ingest + compare endpoint |
| `docs/technical/README.md` | Collection discriminator decision |
| `feature-053` | Step 9 ✅ when merged |

## Implementation Plan

- [ ] **Step 1:** Alembic migration + ORM model update + backfill test.
- [ ] **Step 2:** `collections.py` + router rules (TDD).
- [ ] **Step 3:** Transcript parser + CLI ingest + integration test.
- [ ] **Step 4:** Technical doc parser + ingest.
- [ ] **Step 5:** `chunking_compare` + `POST /api/v1/embeddings/compare`.
- [ ] **Step 6:** Wire collection filter into advanced retrieval + docs.

## Estimation

- Size: **L**
- Estimated time: **8–10 hours**
- Planned steps: **6**

## Pull Request

- Pending `/start-task` after `feature-062` merges.

## How to start

```text
/start-task docs/work-items/feature-063-multi-index-corpus-and-chunking-compare.md
```

Parent: `docs/work-items/feature-053-official-master-parity-alignment.md` Phase 3 Step 9.
Prerequisite: `feature-061` merged to `main` ✅; recommended after `feature-062`.
