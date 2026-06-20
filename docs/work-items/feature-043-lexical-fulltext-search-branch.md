# Feature: Lexical Full-Text Search Branch (Baseline)

> Sub-feature 2 of 7 of the epic `feature-041-retrieval-debug-observability-screen`.
> Depends on: `feature-042-retrieval-debug-api-foundation` (debug API contract + branch container).
> Internal tooling. Not user-facing.

## Why this sub-feature

Pure semantic search fails on the exact cases this project cares about most: technical queries with acronyms, versions, codes, standards, and identifiers (e.g. `RFC 6749`, `JWT`, `OAuth2`, `gpt-4o-mini`). The embedder can rank a semantically-related chunk above one that contains the exact term. To diagnose and tune relevance we need a second, orthogonal retrieval signal — lexical full-text matching — and we need to *see which terms matched*. This is the first non-semantic retrieval capability in the system.

## Objective

Add a reusable **lexical full-text branch** over `chunks.content` using Postgres `websearch_to_tsquery` + `ts_rank_cd`, expose it through the existing debug API as `branches.lexical`, and surface `matched_terms` per result. Baseline uses on-the-fly `to_tsvector` (no migration), consistent with the project's sequential-scan-baseline teaching pattern.

## Value increment (what ships and why it matters)

- `POST /api/v1/retrieval-debug` with `strategies: ["lexical"]` (or including `lexical`) returns a ranked lexical branch with normalized `score` and `matched_terms`.
- Operators can now compare, for the same query, what semantics finds vs what exact text finds — even before fusion exists.
- A clean `LexicalSearchRepository` that sub-features 044 (fusion) and 046 (filters) reuse.

## SMART framing

- **Specific:** one new repository + one new branch in the debug service; no new endpoint.
- **Measurable:** AC-01…AC-10; lexical results include matched lexemes; default suite green offline.
- **Achievable:** standard Postgres FTS, no extra services; baseline needs no migration.
- **Relevant:** provides the exact-term signal the epic exists to expose.
- **Time-boxed:** Size M, ~5 baby steps.

## Context

- `Chunk.content` is `Text`; no `tsvector` column yet (indexed path deferred to optional `feature-048`).
- Debug response already supports a nullable `branches.lexical` slot and `matched_terms` on `DebugResult` (from `feature-042` schemas; extend if a field is missing).
- Reuse `get_db_session` and the debug orchestrator from `feature-042`.

## Handoff from feature-042

Feature-042 shipped the debug API foundation on branch `feature/042-retrieval-debug-api-foundation` and PR `#37`. The next implementation should build on these concrete pieces:

- `POST /api/v1/retrieval-debug` is registered in `app/routers/retrieval_debug.py` and delegates business logic to `app/embedding_pipeline/retrieval_debug.py`.
- `GET /api/v1/retrieval-debug/chunks/{chunk_id}` is already available for full chunk content, previous/next chunk context, parent document metadata, embedding model, and optional query distance/similarity.
- `RetrievalDebugRequest.strategies` already validates `vector`, `lexical`, `hybrid`, `rerank`, and `all`; feature-042 only implements `vector`, so requesting `lexical` currently returns `branches.lexical = null` plus a warning.
- `BranchesContainer` already has nullable branch slots for `vector`, `lexical`, `hybrid`, and `rerank`; `branches.vector[]` uses `BranchResultEntry(rank, chunk_id, document_id, score, distance)`.
- `DebugResult` currently contains vector-specific final-result fields (`semantic_score`, `semantic_rank`, `semantic_distance`) and `source_strategies`. Feature-043 should extend this schema with lexical-specific nullable fields such as `lexical_score`, `lexical_rank`, and `matched_terms`.
- Score convention from 042: vector `score = max(0, min(1, 1 - distance))`; lexical should document its own normalization clearly, likely min-max over branch-local `ts_rank_cd` values.
- Existing explanation helper emits `semantic_strong`, `semantic_weak`, and `below_threshold`. Feature-043 should add lexical explanation signals without weakening the vector-only behavior.
- `retrieval_debug_completed` logging already records safe metadata (`request_id`, `strategies`, `vector_result_count`, `timings_ms`, `max_results`); feature-043 should add lexical counts without logging query text, matched content, embeddings, or secrets.

Important constraints inherited from 042:

- Do not change `POST /api/v1/search`; it remains the stable semantic-search endpoint and has regression coverage.
- Keep OpenAI calls behind `OpenAIEmbedder`; routers should not instantiate provider SDKs directly.
- Empty `DATABASE_URL` must keep returning safe `503` through `get_db_session`.
- Default tests must stay offline with fake embedder/repository/session objects.

Suggested first tests for 043:

- `tests/embedding_pipeline/test_lexical_search_repository.py`: SQL statement contains `websearch_to_tsquery`, `to_tsvector`, `ts_rank_cd`, rank desc ordering, and `top_k` limit.
- `tests/embedding_pipeline/test_retrieval_debug_schemas.py`: lexical config validation and nullable lexical fields on `BranchResultEntry` / `DebugResult` after schema extension.
- `tests/embedding_pipeline/test_retrieval_debug_service.py`: `strategies: ["lexical"]` returns `branches.lexical` instead of warning-only `null`, and `strategies: ["vector", "lexical"]` preserves the vector branch from 042.

## Scope

### Includes

- `app/embedding_pipeline/lexical_search_repository.py`:
  - build statement using `to_tsvector('english', content)` and `websearch_to_tsquery('english', :query)`, ranked by `ts_rank_cd(...) DESC`, limited by `top_k`, `WHERE embedding ... ` not required (lexical operates on content; include all chunks).
  - return rows with `chunk_id`, `document_id`, `chunk_type`, `content`, `metadata`, raw `ts_rank`, and `matched_terms` (lexemes from the query that hit the document; derived via `ts_headline` or query-lexeme intersection).
- Lexical branch in `retrieval_debug.py`: run when requested (incl. `"all"`), min-max normalize `ts_rank` within the branch to `score ∈ [0,1]`, populate `BranchResultEntry` and the lexical fields of `DebugResult`.
- Update single-branch explanation to emit `lexical_exact_match` (and `lexical_only` where applicable) signals.
- Run vector + lexical concurrently with `asyncio.gather` when both requested.
- Repository + service tests; README/technical docs update.

### Excludes

- Rank fusion / diff (044) — branches are returned independently here.
- Indexed FTS / `pg_trgm` (optional `feature-048`).
- Metadata filters (046).
- Frontend (047).

## Functional Requirements

### FR-01 — Lexical branch request

`strategies` may include `"lexical"`; `lexical` config: `{ "top_k": 20 }` (1–50). `"all"` runs every implemented branch.

### FR-02 — Lexical branch response

- `branches.lexical`: list of `{ rank, chunk_id, document_id, score, matched_terms }`, ordered by `ts_rank_cd` desc.
- For chunks present in `final_results`, populate `lexical_score`, `lexical_rank`, `matched_terms`.
- No lexical match for a chunk → its lexical fields are `null`/empty, not zero-filled.
- Empty corpus or no lexical hits → `200` with empty `branches.lexical`.

### FR-03 — Matched terms

`matched_terms` lists the query lexemes that matched the chunk (stemmed, deduplicated). This is the human-facing evidence for the lexical signal and must be deterministic for a given query/content.

### FR-04 — Concurrency & isolation

When both vector and lexical are requested, branches run concurrently; a failure in one branch must not fail the other (partial result + `warnings`), preserving the `feature-042` safety contract.

## Technical Approach

- SQL (illustrative):

```sql
SELECT id, document_id, chunk_type, content, metadata,
       ts_rank_cd(to_tsvector('english', content), websearch_to_tsquery('english', :query)) AS ts_rank
FROM chunks
WHERE to_tsvector('english', content) @@ websearch_to_tsquery('english', :query)
ORDER BY ts_rank DESC
LIMIT :top_k;
```

- `matched_terms`: intersect query lexemes (`to_tsvector('english', :query)`) with document lexemes, or parse `ts_headline` markup; keep it a small pure helper for testability.
- Normalization: min-max over the branch's `ts_rank` values (guard divide-by-zero when all equal).
- No index in this sub-feature: document the sequential-scan baseline and point to optional `feature-048`.

## Acceptance Criteria

- [ ] AC-01: `LexicalSearchRepository` builds a `websearch_to_tsquery` + `ts_rank_cd` statement ordered by rank desc with `top_k` limit (statement compiles; mapping tested).
- [ ] AC-02: `strategies: ["lexical"]` returns `200` with a ranked `branches.lexical`; vector/hybrid/rerank keys `null`.
- [ ] AC-03: Lexical results include `matched_terms` for a query with exact technical tokens (e.g. `JWT`, `OAuth2`).
- [ ] AC-04: `branches.lexical` `score` is normalized to `[0,1]` within the branch.
- [ ] AC-05: `final_results` populate `lexical_score`/`lexical_rank`/`matched_terms` for matched chunks and leave them empty otherwise.
- [ ] AC-06: `strategies: "all"` runs vector + lexical concurrently and returns both branches.
- [ ] AC-07: A lexical-branch failure yields a partial response + `warnings`, not a 500 (vector still returned).
- [ ] AC-08: Empty corpus / no lexical hits → `200` with empty `branches.lexical`.
- [ ] AC-09: `POST /api/v1/search` and the vector branch from `feature-042` remain unchanged.
- [ ] AC-10: Default suite passes offline; README/technical docs explain lexical baseline + matched terms + sequential-scan note.

## Test Plan

- Unit: matched-terms helper; min-max normalization (incl. all-equal guard).
- Repository: statement shape (`websearch_to_tsquery`, `ts_rank_cd`, order, limit) + row mapping with mocked session.
- Service: vector+lexical concurrent run; lexical-only run; partial failure path; lexical fields on `final_results`.
- Manual: Compose Postgres; query with exact tokens vs semantic-only query; confirm lexical surfaces exact-term chunks the vector branch missed.

## Verification

- Automated: `uv run pytest tests/embedding_pipeline -q`.
- Manual: curl debug with `strategies: ["lexical"]` and `"all"` on Compose Postgres; inspect `matched_terms`.
- Not verified yet: fusion/diff (044); indexed FTS performance (048).

## Documentation Plan

- `README.md`: lexical branch in the internal-tools section; note baseline FTS, no index yet.
- `docs/technical/README.md`: SQL shape, normalization, matched-terms derivation, deferral to `feature-048`.
- `docs/arquitectura-estimador-cag.html`: update the retrieval/debug architecture flow to include the lexical branch and sequential-scan baseline.
- Second Brain: note on semantic vs lexical signal differences for technical queries.

## Implementation Plan

- [ ] Step 1: `LexicalSearchRepository` + statement/mapping tests (RED→GREEN).
- [ ] Step 2: Matched-terms helper + normalization helper + unit tests.
- [ ] Step 3: Wire lexical branch into `retrieval_debug.py` (concurrent, partial-failure safe) + service tests.
- [ ] Step 4: Populate lexical fields + `lexical_exact_match` signal in explanation; tests.
- [ ] Step 5: Docs sweep + manual verification.

## Estimation

- Size: M
- Estimated time: 3 hours
- Planned steps: 5
- Depends on: `feature-042-retrieval-debug-api-foundation`
- Unblocks: `feature-044-hybrid-fusion-ranking-diff-explanation`, `feature-046-retrieval-metadata-filters`, `feature-048-indexed-lexical-tsvector-migration`

## Implementation progress

- [x] Step 1: `LexicalSearchRepository` + statement/mapping tests.
- [x] Step 2: Lexical request/response schema extensions.
- [x] Step 3: Lexical normalization and explanation helpers.
- [x] Step 4: Retrieval debug service orchestration for the lexical branch.
- [ ] Step 5: Documentation sweep and final verification.

## Verification log

- Step 1 automated: `uv run pytest tests/embedding_pipeline/test_lexical_search_repository.py -q` (`2 passed`).
- Step 1 lints: no diagnostics in `app/embedding_pipeline/lexical_search_repository.py` or `tests/embedding_pipeline/test_lexical_search_repository.py`.
- Step 2 automated: `uv run pytest tests/embedding_pipeline/test_retrieval_debug_schemas.py -q` (`19 passed`).
- Step 2 regression: `uv run pytest tests/embedding_pipeline/test_retrieval_debug_service.py tests/embedding_pipeline/test_retrieval_debug_vector_branch.py -q` (`8 passed`).
- Step 2 lints: no diagnostics in `app/embedding_pipeline/retrieval_debug_schemas.py` or `tests/embedding_pipeline/test_retrieval_debug_schemas.py`.
- Step 3 automated: `uv run pytest tests/embedding_pipeline/test_retrieval_debug_vector_branch.py -q` (`8 passed`).
- Step 3 regression: `uv run pytest tests/embedding_pipeline/test_retrieval_debug_service.py -q` (`3 passed`).
- Step 3 lints: no diagnostics in `app/embedding_pipeline/retrieval_debug.py` or `tests/embedding_pipeline/test_retrieval_debug_vector_branch.py`.
- Step 4 RED: `uv run pytest tests/embedding_pipeline/test_retrieval_debug_service.py -q` failed before service integration because `run_retrieval_debug()` did not accept `lexical_repository`.
- Step 4 automated: `uv run pytest tests/embedding_pipeline/test_retrieval_debug_service.py -q` (`6 passed`).
- Step 4 logging RED: `uv run pytest tests/embedding_pipeline/test_retrieval_debug_router.py::test_post_retrieval_debug_logs_safe_completion -q` failed before `lexical_result_count` logging existed.
- Step 4 regression: `uv run pytest tests/embedding_pipeline -q` (`170 passed, 2 deselected`).
- Step 4 lints: no diagnostics in edited service, router, or retrieval debug tests.

## Repository commits (master-ia)

| Commit | Summary |
| --- | --- |
| `e1112e9` | Planned the lexical full-text branch implementation and documentation scope before code. |
| `91f5087` | Added the baseline lexical search repository with SQL shape and row-mapping coverage. |
| `106ea18` | Extended retrieval debug schemas for lexical branch configuration and nullable lexical fields. |
| `ae5a181` | Added lexical branch normalization and explanation helpers for retrieval debug. |
