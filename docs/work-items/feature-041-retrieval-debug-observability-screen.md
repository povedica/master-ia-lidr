# Feature (Epic): Internal Retrieval Debugging & Observability Screen

> Internal tooling. Not a user-facing feature.
> Builds on the semantic-search milestone (features 036–040): `POST /api/v1/search`, pgvector cosine distance, HNSW index.
> Introduces the project's first **lexical**, **hybrid**, **diff**, and **rerank-placeholder** retrieval surfaces — all behind a debug-only API and admin screen.
>
> **This document is the EPIC / design reference.** It is not implemented directly. It is split into independently executable sub-features (042–048). Run `/start-task` on the **sub-features** in dependency order, not on this file.

## Sub-feature breakdown (execution order)

Each sub-feature is SMART (specific, measurable, achievable, relevant, time-boxed), can be built and shipped in isolation, and leaves the repo in a working, valuable state. Dependencies are strict: do not start a node before its dependencies are merged.

```text
                       feature-042 (Debug API foundation + vector branch + chunk inspector)
                            │
              ┌─────────────┼───────────────────────────────┐
              ▼             ▼                                 │
   feature-043 (Lexical   feature-046 (Metadata filters)      │
     full-text branch)        ▲                               │
              │               │                               │
              ▼               │                               │
   feature-044 (Hybrid fusion + diff + explanation) ──────────┘
              │
              ▼
   feature-045 (Rerank placeholder / NoOp + signals)
              │
              ▼
   feature-047 (Internal React screen: requirements A–G + states)

   feature-048 (OPTIONAL) Indexed lexical migration (content_tsv + GIN + pg_trgm)
        depends on: feature-043   ·   can land any time after 043
```

| # | Sub-feature | Depends on | Size | Standalone value increment |
|---|-------------|-----------|------|----------------------------|
| 042 | Debug API foundation: schemas + **vector branch** trace + chunk inspector + telemetry skeleton | features 036–040 (existing search) | M | Makes today's vector retrieval **observable & explainable** via a stable API (rank, distance, normalized score, per-result trace, chunk context) without any UI. |
| 043 | **Lexical** full-text branch (baseline on-the-fly `tsvector`) wired into the debug API | 042 | M | Adds exact-term matching for technical queries (acronyms, versions, codes) and exposes `matched_terms` — the first non-semantic retrieval signal in the system. |
| 044 | **Hybrid fusion** (RRF + weighted) + **ranking diff** + **explanation engine** | 042, 043 | M | Turns two independent rankings into consensus/divergence analysis: fused order, big movers, rescued/dropped sets, and human-readable explanations. |
| 045 | **Rerank placeholder** (`NoOpReranker`) + stable interface + rerank signals | 044 | S | Locks the rerank contract and a visible rerank lane so a real reranker plugs in later with zero contract churn; no behavior risk today. |
| 046 | **Metadata filters** across vector & lexical repositories | 042 | S–M | Lets operators scope retrieval (sector, technology, year range, source, tags, language) for precise diagnosis without re-ingesting. |
| 047 | **Internal React screen** (requirements A–G, states, recent searches) | 042–046 | L | Delivers the actual operator-facing debugging UI consuming the full debug API; the headline deliverable of the epic. |
| 048 | (Optional) **Indexed lexical migration** `content_tsv` + GIN + `pg_trgm` | 043 | S | Replaces the lexical sequential-scan baseline with an indexed path; performance/scaling increment, no contract change. |

**Why this order:** 042 establishes the debug API contract and the cheapest valuable increment (observability of existing vector search). 043 adds a second, orthogonal signal. 044 only makes sense once ≥2 branches exist (fusion/diff need something to compare). 045 sits on top of fusion (it reorders the fused list). 046 is repository-level and can be developed in parallel with 043/044 but is sequenced after 042 because it extends the branch queries. 047 needs the API surface complete. 048 is a pure optimization gated behind 043.

The detailed design below is shared context for all sub-features; each sub-feature restates only its own scope, acceptance, and verification.

## Handoff from feature-043

Feature-043 (`feature/043-lexical-fulltext-search-branch`, PR `#39`) completed the lexical full-text baseline that unlocks feature-044. This epic-level handoff captures the state that downstream sub-features should assume:

- The debug API now has two implemented retrieval signals: `vector` and `lexical`. `hybrid` and `rerank` are still reserved branch slots and warning-producing future strategies.
- `app/embedding_pipeline/lexical_search_repository.py` introduces `LexicalSearchRepository` and `LexicalSearchResult`. The SQL baseline uses `websearch_to_tsquery`, on-the-fly `to_tsvector('english', chunks.content)`, `ts_rank_cd`, and `ts_headline`; no indexed `tsvector` or `pg_trgm` path exists yet.
- `branches.lexical[]` emits `rank`, `chunk_id`, `document_id`, normalized `score`, and `matched_terms`; `distance` is `null` for lexical rows.
- `final_results[]` can now carry nullable semantic fields plus `lexical_score`, `lexical_rank`, and `matched_terms`. When vector and lexical agree on a chunk, `source_strategies` includes both branches.
- `run_retrieval_debug()` accepts injectable vector and lexical repositories, runs requested branches with partial-failure isolation, and keeps safe warnings instead of failing the whole request when one branch errors.
- Logging remains safe: `retrieval_debug_completed` records branch counts and timings but not query text, chunk content, embeddings, or secrets.
- Documentation was synchronized in `README.md`, `docs/technical/README.md`, `docs/arquitectura-estimador-cag.html`, and the canonical feature-043 work item.

Verification carried from feature-043:

- `uv run pytest tests/embedding_pipeline -q` (`170 passed, 2 deselected`).
- `uv run pytest` (`561 passed, 11 skipped, 12 deselected`).

Residual risk / follow-ups:

- Live Compose/Postgres curl smoke for `strategies: ["lexical"]` and `"all"` was not run during feature-043 closure.
- Feature-044 should centralize explanation generation; feature-043 only added the first lexical signal (`lexical_exact_match`) beside the existing vector helper.
- Feature-048 remains responsible for indexed lexical performance; feature-043 intentionally ships a sequential-scan teaching baseline.

## Handoff from feature-048

Feature-048 (`feature/048-indexed-lexical-tsvector-migration`, PR `#44`) completed the optional indexed lexical path for the retrieval debug epic:

- Alembic migration `0003_add_chunks_content_tsv_and_trgm.py` adds `pg_trgm`, generated `chunks.content_tsv`, `ix_chunks_content_tsv_gin`, and `ix_chunks_content_trgm`.
- `LexicalSearchRepository` now ranks with `ts_rank_cd(content_tsv, websearch_to_tsquery(...))` and filters with `content_tsv @@ ...`, replacing the feature-043 on-the-fly `to_tsvector` baseline.
- The retrieval-debug API contract did not change: lexical branch rows and final-result lexical fields keep the same shape and `matched_terms` behavior.
- Manual Compose verification showed `Bitmap Index Scan on ix_chunks_content_tsv_gin`; downgrade to `0002` removed `content_tsv`, and the local DB was upgraded back to `0003 (head)`.
- Rollback note: DB downgrade to `0002` should be paired with app code rollback to the feature-043 baseline because feature-048 code expects `content_tsv`.

Residual risk / follow-ups:

- Large-corpus latency benchmarks and production `CREATE INDEX CONCURRENTLY` behavior remain out of scope.
- A future feature may use `pg_trgm` for explicit similarity scoring; feature-048 only provisions the extension/index and keeps the HTTP contract unchanged.

## Handoff from feature-044

Feature-044 (`feature/044-hybrid-fusion-ranking-diff-explanation`, PR `#40`) completed hybrid rank fusion, ranking diff, and the controlled explanation engine that unlock feature-045. This epic-level handoff captures the state that downstream sub-features should assume:

- `POST /api/v1/retrieval-debug` now accepts `hybrid` config with `enabled`, `method: "rrf"|"weighted"`, `rrf_k`, and optional branch `weights`.
- `strategies` can include `hybrid`; `strategies: ["all"]` resolves to vector, lexical, hybrid, and future rerank warning.
- `branches.hybrid[]` exposes fused rank entries with `rank`, `chunk_id`, `document_id`, and `score`.
- Hybrid `final_results[]` are ordered by `fusion_rank`, capped by `max_results`, and include `fusion_score`, semantic evidence, lexical evidence, `source_strategies`, metadata, excerpt, and controlled explanations.
- `diff` now reports `common`, `vector_only`, `lexical_only`, `hybrid_rescued`, `big_movers`, `dropped_by_threshold`, and `dropped_by_rerank`.
- `RetrievalDebugRequest` includes `hybrid`; `method="weighted"` without weights returns `422`.
- `DebugResult` includes nullable `fusion_score` and `fusion_rank`.
- `RetrievalDebugResponse` includes nullable `diff`; it is present for enabled hybrid responses and `null` for vector/lexical-only or disabled hybrid fallback.
- `timings_ms` includes a `hybrid` key.
- Controlled explanation signals are centralized in `app/embedding_pipeline/fusion.py`.

Verification carried from feature-044:

- `uv run pytest tests/embedding_pipeline/test_fusion.py -q` — passed during Steps 1–3.
- `uv run pytest tests/embedding_pipeline/test_retrieval_debug_schemas.py -q` — `23 passed`.
- `uv run pytest tests/embedding_pipeline/test_fusion.py tests/embedding_pipeline/test_retrieval_debug_schemas.py tests/embedding_pipeline/test_retrieval_debug_service.py -q` — `35 passed`.
- `uv run pytest tests/embedding_pipeline -q` — `180 passed, 2 deselected`.
- `uv run pytest` — `571 passed, 11 skipped, 12 deselected`.

Residual risk / follow-ups:

- Live Compose/Postgres curl smoke for `strategies: ["vector", "lexical", "hybrid"]`, `"all"`, weighted config, and `enabled=false` was not run during feature-044 closure.
- Rerank behavior remains out of scope; `dropped_by_rerank` stays empty until feature-045.
- Hybrid rescue and big-mover thresholds are deterministic constants in the service; future UI work may tune them after real corpus inspection.
- RRF scores are intentionally raw RRF contributions, while weighted fusion scores are normalized weighted sums; UI labels should avoid comparing them as the same scale.

## Handoff from feature-045

Feature-045 (`feature/045-rerank-placeholder-interface`, PR `#41`) completed the rerank placeholder interface that downstream UI and filter work should assume:

- `app/embedding_pipeline/rerank.py` defines the stable `Reranker` protocol, `RerankCandidate`, `RerankedItem`, and `NoOpReranker`.
- `POST /api/v1/retrieval-debug` accepts `rerank.enabled` (default `false`). When enabled with no injected real reranker, the default no-op preserves order and emits `rerank.enabled=true but no reranker configured; rerank is a no-op placeholder`.
- `branches.rerank[]` is present only when rerank runs; `final_results[]` include nullable `rerank_score` and `rerank_rank`, and `source_strategies` gains `rerank`.
- Fake reorder/filter rerankers in tests prove the contract can represent `rerank_promoted`, `rerank_demoted`, and `diff.dropped_by_rerank` without a real model.
- `timings_ms` includes `rerank`.

Verification carried from feature-045:

- `uv run pytest tests/embedding_pipeline -q` — `187 passed, 2 deselected`.
- `uv run pytest` — `578 passed, 11 skipped, 12 deselected`.

Residual risk / follow-ups:

- Live Compose/Postgres curl smoke for `rerank.enabled=true` was not run during feature-045 closure.
- A future real reranker may need full chunk content in `RerankCandidate.content`; the current no-op path uses the final result excerpt and does not affect the HTTP response contract.
- Feature-046 should verify filters compose with rerank enabled after vector/lexical candidate narrowing.

## Handoff from feature-046

Feature-046 (`feature/046-retrieval-metadata-filters`, PR `#42`) completed metadata filters for the retrieval debug branches:

- `RetrievalMetadataFilters` supports `document_type`, `client_sector`, `main_technology`, `source_name`, `language`, `tags`, and inclusive `year` bounds.
- Vector and lexical repositories apply filters before branch ranking and limiting; empty filters normalize away and unknown keys remain ignored by schema validation.
- `applied_config.filters` echoes normalized filters so the UI can show the exact scoped candidate set.
- The implementation keeps production `POST /api/v1/search` unchanged and confines filters to the debug retrieval path.

Verification carried from feature-046:

- `uv run pytest tests/embedding_pipeline -q` — `200 passed, 2 deselected`.
- `uv run pytest` — `589 passed, 11 skipped, 12 deselected`.

Residual risk / follow-ups:

- Live Compose/Postgres smoke with realistic filter combinations was not run during feature-046 closure.
- Large-corpus planner behavior for JSONB filters and year casts remains a performance follow-up, not a contract blocker.

## Handoff from feature-047

Feature-047 (`feature/047-retrieval-debug-internal-screen`, PR `#43`) completed the operator-facing React screen and closes the epic's headline deliverable:

- `/debug/retrieval` is gated behind `VITE_ENABLE_RETRIEVAL_DEBUG=true` and is not part of normal end-user navigation.
- The screen consumes the existing debug API contract and renders query/strategy input, full tuning controls, metadata filters, recent searches, comparative results, explanation chips, branch rankings, ranking diff, non-blocking warnings, and a chunk inspector drawer.
- The chunk inspector now displays full chunk context, distance/similarity, and lexical `matched_terms` when a query is provided, aligning AC-14 with the UI.
- Frontend Zod schemas mirror the retrieval debug request, response, ranking diff, and chunk inspection contracts.
- Documentation is synchronized in `README.md`, `web/README.md`, `web/.env.example`, `docs/technical/README.md`, `docs/arquitectura-estimador-cag.html`, the feature-047 work item, and the Second Brain learning note.

Verification carried from feature-047:

- `cd web && npm test` — `48 passed`.
- `cd web && npm run build` — passed.
- `cd web && npm run lint` — passed.
- `uv run pytest tests/embedding_pipeline/test_retrieval_debug_schemas.py::test_chunk_inspection_response_exposes_document_and_embedding_metadata tests/embedding_pipeline/test_retrieval_debug_router.py::test_chunk_inspector_returns_context_and_optional_similarity -q` — `2 passed`.
- `cd web && npm test -- --run src/features/retrieval-debug/components/RetrievalDebugPage.test.tsx` — `10 passed`.

Residual risk / follow-ups:

- Live Compose/Postgres end-to-end screen smoke with an ingested corpus remains manual and not yet executed.
- The internal route is guarded by a frontend build-time flag only; production authz remains out of scope.
- Formal accessibility review and screenshot capture for class/demo material remain follow-ups.

## Epic closure status

The epic is implemented through sub-features 042-047, with optional performance feature-048 also shipped. The remaining work is operational hardening and validation (live smoke, authz, accessibility, persisted debug runs), not core feature completion.

## Objective

Provide an internal screen and supporting API to inspect and tune the **retrieval stage** of the RAG system. The goal is to make retrieval explainable instead of a black box: given a natural-language query, an operator must see *which* chunks are retrieved, *which strategy* retrieved them, *with what score/rank*, *how the ranking changes when strategies are combined*, and *which signals explain the final order*.

This is a learning and tuning tool for relevance diagnosis, with first-class support for technical queries that mix semantics with exact terms (technologies, acronyms, proper nouns, versions, codes, standards, identifiers).

## Context

### Existing retrieval (real APIs)

- `POST /api/v1/search` (`app/routers/search.py` → `app/embedding_pipeline/search.py:run_semantic_search`) is the **only** retrieval endpoint today. It is **vector-only**.
- Ranking uses `ChunkModel.embedding.cosine_distance(query_vector)` in `SemanticSearchRepository.build_search_statement()` (`app/embedding_pipeline/search_repository.py`); lower distance = more similar.
- Query embedding via `OpenAIEmbedder.embed_one()` (`app/embedding_pipeline/embedder.py`), model `text-embedding-3-small`, dim `1536` (`EMBEDDING_PIPELINE_MODEL`).
- Storage: Postgres + pgvector. ORM models `Document` (`app/models/document.py`) and `Chunk` (`app/models/chunk.py`). `Chunk` has `chunk_type`, `content`, `embedding (Vector(1536), nullable)`, `metadata_ (JSONB)`, `document_id`.
- Indexes: GIN on `chunks.metadata` (`ix_chunks_metadata_gin`), HNSW cosine on `chunks.embedding` (`ix_chunks_embedding_hnsw`, feature-040).
- Typical chunk metadata keys (from `app/embedding_pipeline/chunker.py`): `budget_id`, `component_id`, `client_sector`, `main_technology`, `year`, `complexity`, `estimated_hours`, `source_name`.
- Current `SearchResponse`: `{ query, k, search_time_ms, results[] }`, where each result has `chunk_id`, `document_id`, `chunk_type`, `content`, `distance`, `metadata`.

### What does NOT exist yet (this feature introduces it as debug-scoped)

- **Lexical / full-text search.** No `tsvector` column, no BM25, no trigram matching.
- **Hybrid search / rank fusion.** No RRF, no weighted fusion.
- **Reranking.** No cross-encoder or LLM reranker.
- **Metadata filters in SQL.** GIN index exists but search ignores it.
- **Any retrieval UI.** The React app (`web/`, React 19 + TS + Vite 8 + Tailwind 4 + Zod, Vitest) only consumes estimation/session APIs. There is no search or admin screen.

### Constraints and conventions

- Routers register under `/api/v1` in `app/main.py`; route handlers orchestrate, services own logic, providers/SDKs are never called from handlers (`.cursor/rules/02-fastapi-standards.mdc`, `03-ai-engineering-standards.mdc`).
- DB endpoints depend on `get_db_session`; when `DATABASE_URL` is empty they must fail with a safe `503` (existing pattern).
- Tests mock OpenAI; default suite must not need real keys or live Postgres (`.cursor/rules/05-testing-standards.mdc`).
- This is a **strict-mode** work item (new settings, multiple modules/layers, frontend↔backend contract). During `/start-task` it should be split into baby-step increments (see Implementation Plan) and may be promoted to several sub-features if it grows.

## Scope

### Includes

- A debug-only retrieval API (`POST /api/v1/retrieval-debug`) returning per-branch rankings, a fused ranking, a per-result trace, a ranking diff, timings, and warnings.
- A chunk-inspection endpoint (`GET /api/v1/retrieval-debug/chunks/{chunk_id}`) returning full content, neighbor context, full metadata, embedding model, chunk type, and (optionally) per-query distance and matched lexical terms.
- New backend retrieval branches reused by the debug service:
  - **Vector** branch — reuse the existing semantic search path, exposing rank + distance + a normalized score.
  - **Lexical** branch — Postgres full-text (`websearch_to_tsquery` + `ts_rank_cd`) over `chunks.content`, with optional `pg_trgm` similarity for exact technical tokens.
  - **Hybrid** branch — rank fusion (Reciprocal Rank Fusion by default; configurable weighted fusion).
  - **Rerank** branch — explicit no-op placeholder with a stable interface so a future cross-encoder/LLM reranker plugs in without contract changes.
- Metadata filters applied at the repository level (document type, sector, technology, year, source, tags, language) when present in `chunks.metadata` / `documents`.
- A new internal React screen under `web/` (admin/debug route) implementing requirements A–G below, including loading/error/empty states and recent-search reuse.
- Structured telemetry and logs for each debug run (no secrets, no full embeddings).
- Deterministic unit/service/router tests with fake embedder, fake lexical results, and seeded rankings; frontend component tests with mocked API.
- Documentation: README internal-tools section, `docs/technical/README.md`, architecture HTML, and a Second Brain session note.

### Excludes

- Exposing this screen to end users or wiring it into the estimation flow.
- A real reranker model (only the interface + placeholder; real reranking is a follow-up).
- Changing the production `POST /api/v1/search` contract (debug endpoint is additive).
- Re-embedding or re-chunking the corpus; no ingest changes beyond the optional lexical migration.
- Real OpenAI/Anthropic calls in the default test suite.
- Authn/authz hardening of the admin route beyond a simple build-time/env gate (documented as follow-up).
- Pagination, result export, or persistence of debug runs (future extensions).

## Functional Requirements

### FR-01 — Query box (requirement A)

- Single natural-language text input plus a **Search** button.
- Strategy selector: `vector`, `lexical`, `hybrid`, or `all` (compare every branch).
- Recent searches: persist the last N queries + their config locally (browser `localStorage`) and allow one-click reuse. No server-side persistence in this feature.

### FR-02 — Tuning controls (requirement B)

The request must let the operator configure:

- `top_k` per branch (vector, lexical).
- Semantic `threshold` (max cosine distance, or min normalized similarity) to drop weak vector hits.
- `max_results` for the final fused list.
- Hybrid fusion: enable/disable, method (`rrf` | `weighted`), `rrf_k`, and per-branch `weights`.
- Reranking: enable/disable (placeholder — when enabled with no real model, the response must clearly flag it as a no-op and return rerank ranks equal to input order).
- Metadata filters when the index supports the key: `document_type`, `client_sector`, `main_technology`, `year` (range), `source_name`, `tags`, `language`. Unknown/empty filters are ignored.

All tuning values have safe defaults and validated bounds; invalid values return `422`.

### FR-03 — Debug search request

Effective route:

```text
POST /api/v1/retrieval-debug
```

Request body (illustrative):

```json
{
  "query": "JWT refresh token rotation for OAuth2 REST API (RFC 6749)",
  "strategies": ["vector", "lexical", "hybrid"],
  "vector": { "top_k": 20, "threshold": null },
  "lexical": { "top_k": 20, "use_trigram": true },
  "hybrid": { "enabled": true, "method": "rrf", "rrf_k": 60, "weights": { "vector": 0.5, "lexical": 0.5 } },
  "rerank": { "enabled": false },
  "max_results": 15,
  "filters": { "client_sector": "finance", "year": { "from": 2023, "to": 2025 } }
}
```

Validation:

- `query`: non-empty after trimming.
- `strategies`: non-empty subset of the supported branches, or `"all"`.
- `top_k`: `1..50`; `max_results`: `1..50`.
- `threshold`: optional float in a documented range.
- `weights`: non-negative; normalized server-side; required only when `method = "weighted"`.

### FR-04 — Debug response data model (requirements C, D, E, F)

The response must expose enough structure to render the comparative table, per-result explanation, per-branch tabs, and ranking diff without further calls.

```json
{
  "query": "JWT refresh token rotation for OAuth2 REST API (RFC 6749)",
  "applied_config": { "...": "echo of normalized request config" },
  "timings_ms": { "vector": 41, "lexical": 12, "hybrid": 1, "rerank": 0, "total": 58 },
  "branches": {
    "vector":  [ { "rank": 1, "chunk_id": 12, "document_id": 7, "score": 0.83, "distance": 0.41 } ],
    "lexical": [ { "rank": 1, "chunk_id": 99, "document_id": 7, "score": 0.77, "matched_terms": ["jwt","oauth2"] } ],
    "hybrid":  [ { "rank": 1, "chunk_id": 12, "document_id": 7, "score": 0.0312 } ],
    "rerank":  null
  },
  "final_results": [
    {
      "final_position": 1,
      "chunk_id": 12,
      "document_id": 7,
      "title": "BUD-2024-014 · OAuth 2.0 authentication backend",
      "content_excerpt": "Backend service with JWT access/refresh tokens...",
      "semantic_score": 0.83, "semantic_rank": 1, "semantic_distance": 0.41,
      "lexical_score": 0.62, "lexical_rank": 3, "matched_terms": ["jwt", "oauth2"],
      "fusion_score": 0.0312, "fusion_rank": 1,
      "rerank_score": null, "rerank_rank": null,
      "source_strategies": ["vector", "lexical", "hybrid"],
      "metadata": { "budget_id": "BUD-2024-014", "client_sector": "finance" },
      "explanation": {
        "summary": "Top result by consensus: ranked #1 by vector and present in lexical via exact terms 'jwt'/'oauth2'; hybrid fusion kept it first.",
        "signals": ["semantic_strong", "lexical_exact_match", "branch_consensus"]
      }
    }
  ],
  "diff": {
    "common": [12, 7],
    "vector_only": [31],
    "lexical_only": [99],
    "hybrid_rescued": [99],
    "big_movers": [ { "chunk_id": 31, "from_rank": 2, "to_rank": 9, "branch_from": "vector", "branch_to": "hybrid", "delta": -7 } ],
    "dropped_by_threshold": [44],
    "dropped_by_rerank": []
  },
  "warnings": ["rerank.enabled=true but no reranker configured; rerank is a no-op placeholder"]
}
```

Behavior:

- Empty corpus → `200` with empty branches/results and no error.
- Each branch that was not requested is `null` (not `[]`).
- `score` per branch is a documented, normalized 0–1 value for comparability; raw signals (`distance`, `ts_rank`, fusion score) are also surfaced where applicable.
- `source_strategies` lists every branch in which a chunk appeared at/above its `top_k`.
- `explanation.signals` uses a stable controlled vocabulary (e.g. `semantic_strong`, `semantic_weak`, `lexical_exact_match`, `branch_consensus`, `hybrid_rescued`, `rerank_promoted`, `rerank_demoted`, `below_threshold`) so the UI can render labels deterministically; `explanation.summary` is human-readable technical English.

### FR-05 — Chunk inspection (requirement G)

```text
GET /api/v1/retrieval-debug/chunks/{chunk_id}?query=<optional>
```

Returns:

- Full `content` of the chunk.
- Neighbor context: previous/next chunk in the same `document_id` (by id order) and parent `Document` reference (`source_path`, `document_type`, document metadata).
- Full chunk `metadata`.
- `embedding_model` used (`EMBEDDING_PIPELINE_MODEL`) and `embedding_present` boolean.
- `chunk_type` and, when available in metadata, the chunking strategy.
- When `query` is provided: cosine `distance`/similarity for that chunk and `matched_terms` from the lexical analyzer.

Unknown `chunk_id` → `404`.

### FR-06 — States (loading / error / empty)

- **Loading:** per-branch progress while the request is in flight; disable Search to prevent duplicate submits.
- **Error:** safe message for `422` (validation), `503` (DB unavailable / `DATABASE_URL` empty), and `5xx`; never expose stack traces or secrets.
- **Empty:** distinct "no results" state (valid query, empty branches) separate from "not searched yet".
- **Partial:** if one branch fails (e.g. lexical) but others succeed, render available branches and surface the failure in `warnings` rather than failing the whole run.

## Technical Approach

### Backend layout

| File | Responsibility |
|------|----------------|
| `app/routers/retrieval_debug.py` | `POST /retrieval-debug`, `GET /retrieval-debug/chunks/{id}`; DI for session, embedder, repositories, debug service; maps errors to safe HTTP responses. Registered under `/api/v1` in `app/main.py`. |
| `app/embedding_pipeline/retrieval_debug.py` | Orchestration service: run requested branches concurrently, apply threshold/filters, fuse, run rerank placeholder, build per-result trace, compute diff, assemble timings/warnings. |
| `app/embedding_pipeline/lexical_search_repository.py` | Postgres full-text query (`websearch_to_tsquery('english', :q)` + `ts_rank_cd`) and optional `pg_trgm` similarity; returns ranked rows + matched terms. |
| `app/embedding_pipeline/fusion.py` | Pure functions: `reciprocal_rank_fusion(branches, k)` and `weighted_fusion(branches, weights)`; fully unit-testable. |
| `app/embedding_pipeline/rerank.py` | `Reranker` protocol + `NoOpReranker` placeholder returning input order; future real reranker implements the same interface. |
| `app/embedding_pipeline/retrieval_debug_schemas.py` | Pydantic request/response models described in FR-03/FR-04/FR-05. |
| `app/embedding_pipeline/search_repository.py` | Reused; extend with optional metadata-filter `WHERE` clauses and exposing rank/normalized score for the debug path (keep `POST /search` unchanged). |

Concurrency: run vector and lexical branches with `asyncio.gather`; fusion/rerank are CPU-cheap and synchronous on the gathered results.

### Lexical search options (decision recorded in spec)

- **Baseline (no migration):** compute `to_tsvector('english', content)` on the fly with `ts_rank_cd`. Acceptable for the course corpus size, consistent with the project's "sequential-scan baseline first" teaching pattern (feature-038/040). Returns matched lexemes for the explanation column.
- **Optimized (optional migration `0003`):** add a generated `content_tsv tsvector` column + GIN index and enable `pg_trgm` for exact technical tokens. Treated as a later baby step; the debug service must work with the baseline first.

### Normalization & fusion

- Vector: `similarity = 1 - cosine_distance`; normalized to `[0,1]`. Threshold compares against this similarity (documented).
- Lexical: min-max normalize `ts_rank_cd` within the branch.
- Hybrid RRF: `score = Σ_branch weight_branch / (rrf_k + rank_branch)`; default `rrf_k = 60`, equal weights.
- Weighted fusion: normalized per-branch scores combined by provided weights.

### Frontend layout (`web/`)

New internal route (e.g. `/debug/retrieval`), gated behind an env/build flag (`VITE_ENABLE_RETRIEVAL_DEBUG`) and excluded from the end-user navigation.

| Component | Maps to requirement |
|-----------|---------------------|
| `RetrievalDebugPage` | Page shell, state machine (idle/loading/error/empty/partial/results). |
| `QueryBox` | A — input, Search, strategy selector, recent searches (localStorage). |
| `TuningPanel` | B — top-k, threshold, max results, fusion config, rerank toggle, metadata filters. |
| `ComparativeResultsTable` | C — one row per final result with all score/rank/strategy/metadata columns. |
| `ResultExplanation` | D — explanation summary + signal chips per result. |
| `BranchTabs` | E — tabs/columns for vector / lexical / hybrid / rerank rankings. |
| `RankingDiffView` | F — common, branch-exclusive, big movers, hybrid-rescued, dropped. |
| `ChunkInspectorDrawer` | G — full content, neighbors, metadata, embedding model, distance, matched terms. |

Use the existing API client patterns under `web/src/features/...` and Zod schemas mirroring the backend response. Add a typed `retrievalDebugApi.ts`.

### Telemetry & logs (requirement 7)

- Structured log `retrieval_debug_completed` with stable keys: `request_id`, `strategies`, per-branch result counts, per-branch + total `timings_ms`, `max_results`, `fusion_method`, `rerank_enabled`, `corpus_eligible`. No query text by default if it may contain sensitive data (configurable), no embeddings, no API keys.
- `retrieval_debug_branch_failed` warning log with `branch` and `error_type` (no payloads).
- Reuse existing logging conventions (`semantic_search_completed`/`_failed`).
- Optional, behind existing observability flags: OTel span per branch / Langfuse event. Document as optional; do not hard-require.

## Acceptance Criteria

- [x] AC-01: `POST /api/v1/retrieval-debug` and `GET /api/v1/retrieval-debug/chunks/{id}` appear in OpenAPI under `/api/v1`.
- [x] AC-02: A valid request with `strategies: "all"` returns `200` with `branches` for vector, lexical, hybrid, and a rerank placeholder, plus `final_results`, `diff`, `timings_ms`, and `warnings`.
- [x] AC-03: Vector branch reuses the existing cosine-distance path and exposes `rank`, `distance`, and a normalized `score`; production `POST /api/v1/search` behavior is unchanged.
- [x] AC-04: Lexical branch returns ranked rows with `matched_terms` for a query containing exact technical tokens (e.g. `JWT`, `OAuth2`).
- [x] AC-05: Hybrid branch applies RRF by default and reflects configurable `method`/`weights`/`rrf_k`; disabling fusion omits the hybrid branch.
- [x] AC-06: Each `final_results` item includes final position, chunk id, document id, title/reference, excerpt, semantic score/rank/distance, lexical score/rank, fusion score/rank, rerank score/rank (nullable), `source_strategies`, metadata, and a structured `explanation`.
- [x] AC-07: `explanation.signals` uses the controlled vocabulary and correctly flags consensus, hybrid-rescue, below-threshold, and rerank no-op cases in deterministic tests.
- [x] AC-08: `diff` reports common, per-branch-exclusive, hybrid-rescued, big-movers, and dropped-by-threshold/rerank sets consistently with the branch rankings.
- [x] AC-09: Threshold drops weak vector hits and they appear in `diff.dropped_by_threshold`; `max_results` limits the final list.
- [x] AC-10: Metadata filters restrict candidates per branch; unknown/empty filters are ignored without error.
- [x] AC-11: `rerank.enabled=true` with no real model returns rerank ranks equal to input order and a clear `warnings` entry (no-op placeholder).
- [x] AC-12: Empty corpus returns `200` with empty branches/results; invalid input returns `422`; empty `DATABASE_URL` returns a safe `503`.
- [x] AC-13: A failing single branch yields a partial response (other branches present) with a `retrieval_debug_branch_failed` warning, not a 500.
- [x] AC-14: `GET /retrieval-debug/chunks/{id}` returns full content, neighbor context, full metadata, embedding model, chunk type, and per-query distance/matched terms when `query` is provided; unknown id → `404`.
- [x] AC-15: The internal React screen implements requirements A–G with loading, error, empty, and partial states and recent-search reuse, gated behind `VITE_ENABLE_RETRIEVAL_DEBUG`.
- [x] AC-16: Structured logs are emitted for debug runs and branch failures without secrets, embeddings, or API keys.
- [x] AC-17: Default test suite passes without real API keys or live Postgres (mocked embedder, fake lexical/branch results, mocked frontend API).
- [x] AC-18: README, technical docs, architecture HTML, and a Second Brain note describe the screen, the debug API contract, and how to read scores/diff/explanations.

## Test Plan

- Unit tests:
  - `fusion.py`: RRF and weighted fusion ordering, tie handling, `rrf_k` effect, weight normalization.
  - normalization helpers (vector similarity, lexical min-max, threshold filtering).
  - explanation builder: each controlled-vocabulary signal from crafted branch inputs.
  - diff builder: common / exclusive / movers / rescued / dropped from synthetic rankings.
  - request schema validation (bounds, `strategies` subset, weighted-requires-weights).
- Service tests (`retrieval_debug.py`):
  - fake embedder + fake lexical repository + seeded vector rows → assert per-branch ranks, fused order, trace fields, timings present, warnings for no-op rerank.
  - partial failure path (lexical raises) → partial response + warning.
  - threshold and `max_results` effects; metadata filter narrowing.
- Repository tests:
  - lexical SQL statement shape (`websearch_to_tsquery`, `ts_rank_cd`) and metadata-filter `WHERE` clauses compile and map rows (mocked session).
  - search repository metadata-filter extension does not change default `/search` query.
- Router tests:
  - OpenAPI routes exist; `200` happy path with overrides; `422` validation; `503` when DB unavailable; `404` unknown chunk.
- Frontend tests (Vitest):
  - components render results/branches/diff from a mocked response; loading/error/empty/partial states; recent-search reuse; chunk drawer opens with neighbor context.
- Manual checks:
  - Compose Postgres + ingested corpus; run vector/lexical/hybrid/all; verify diff and explanations against `EXPLAIN`-level intuition; inspect a chunk; toggle threshold/rerank and observe diff changes.

## Verification

- Automated: `uv run pytest tests/embedding_pipeline -q` (debug service, fusion, repositories, router) and `cd web && npm test` (or project equivalent) for the screen.
- Manual: documented curl examples for `POST /api/v1/retrieval-debug` and the chunk inspector against Compose Postgres, plus a screenshot/notes of the screen in each state.
- Not verified yet (until `/start-task`): real reranker quality, large-corpus latency, integration test against live Postgres in CI.

## Documentation Plan

- `README.md`: new "Internal tools → Retrieval debugging screen" subsection with purpose, env flag, run commands, and a curl example; note it is internal-only.
- `docs/technical/README.md`: debug API contract, branch normalization/fusion math, explanation vocabulary, lexical baseline vs optional migration, telemetry keys.
- `docs/arquitectura-estimador-cag.html`: add the retrieval-debug router/service node and API table rows; mark lexical/hybrid/rerank as debug-scoped.
- Second Brain: `learnings/docs/sesiones/sesion-NN-retrieval-debug-observability.md` capturing what hybrid fusion and the diff view teach about semantic vs lexical trade-offs on technical queries.
- `.env.example`: document any new variables (e.g. lexical/fusion defaults, `VITE_ENABLE_RETRIEVAL_DEBUG`) with placeholder/empty values.

## Implementation Plan

This epic is **not implemented directly**. Implementation is delegated to the sub-features in dependency order. Each sub-feature owns its own baby-step plan, tests, and verification.

- [x] `feature-042-retrieval-debug-api-foundation.md` — debug API + vector branch + chunk inspector.
- [x] `feature-043-lexical-fulltext-search-branch.md` — lexical full-text branch.
- [x] `feature-044-hybrid-fusion-ranking-diff-explanation.md` — fusion + diff + explanation.
- [x] `feature-045-rerank-placeholder-interface.md` — NoOp reranker + signals.
- [x] `feature-046-retrieval-metadata-filters.md` — metadata filters across branches.
- [x] `feature-047-retrieval-debug-internal-screen.md` — React screen (A–G + states).
- [x] `feature-048-indexed-lexical-tsvector-migration.md` — (optional) indexed lexical path.

Start with: `/start-task docs/work-items/feature-042-retrieval-debug-api-foundation.md`

## Sub-feature split report

This epic was split into seven independently executable sub-features on 2026-06-20. All sub-feature documents have been written under `docs/work-items/` (spec-only; no `app/`, `web/`, or `tests/` changes). The split satisfies the requested constraints: each node is **SMART**, runs **in isolation in dependency order**, and ships a **distinct software increment of value**.

### Delivered documents

| # | File | Status | Depends on | Size | Why this sub-feature (one line) |
|---|------|--------|-----------|------|---------------------------------|
| 042 | `feature-042-retrieval-debug-api-foundation.md` | Shipped | 036–040 | M | Make existing vector retrieval observable/explainable via a stable debug API + chunk inspector. |
| 043 | `feature-043-lexical-fulltext-search-branch.md` | Shipped | 042 | M | Add the first non-semantic signal: exact-term lexical matching with `matched_terms`. |
| 044 | `feature-044-hybrid-fusion-ranking-diff-explanation.md` | Shipped | 042, 043 | M | Combine + compare branches: fusion, consensus/divergence diff, explanation engine. |
| 045 | `feature-045-rerank-placeholder-interface.md` | Shipped | 044 | S | Lock the rerank contract now (NoOp) so a real reranker is a drop-in later. |
| 046 | `feature-046-retrieval-metadata-filters.md` | Shipped | 042 | S–M | Scope the corpus (sector/year/tags…) to isolate variables when tuning. |
| 047 | `feature-047-retrieval-debug-internal-screen.md` | Shipped | 042–046 | L | The operator-facing screen (requirements A–G + states): the headline deliverable. |
| 048 | `feature-048-indexed-lexical-tsvector-migration.md` | Shipped (optional) | 043 | S | Replace the lexical sequential-scan baseline with an indexed `content_tsv` + GIN + `pg_trgm` path. |

### Mandatory blocks present in every sub-feature

Each document above includes, beyond the standard `/start-task` strict-gate sections (objective, context, scope, functional requirements, technical approach, acceptance criteria, test plan, verification, documentation plan, baby-step implementation plan):

- `## Why this sub-feature` — the rationale / explanation requested.
- `## Objective` — the concrete goal.
- `## Value increment (what ships and why it matters)` — the valuable software increment.
- `## SMART framing` — Specific / Measurable / Achievable / Relevant / Time-boxed justification.

### Execution guidance

- Recommended order: **042 → 043 → 044 → 045 → 046 → 047**; **048** may land any time after 043.
- 046 may be developed in parallel with 043/044 but must be sequenced after 042 (it extends branch queries).
- Do not start a node before its dependencies are merged (strict dependencies; see the graph above).
- This epic file is **not** a `/start-task` target; start with the sub-features.

## Future Extensions (requirement 8)

- Real reranking (cross-encoder or LLM-as-reranker) implementing the `Reranker` protocol; surface `rerank_score`/`rerank_rank` and `rerank_promoted`/`rerank_demoted` signals already modeled.
- Persisted debug runs + side-by-side comparison of two configs (A/B tuning).
- Saved query sets / regression "golden retrieval" snapshots reusing `tests/evals` patterns.
- Per-query export (CSV/JSON) and shareable permalinks.
- Indexed lexical path (`content_tsv` + GIN + `pg_trgm`) and BM25 via an external engine if needed.
- Filterable telemetry dashboard combining `pg_stat_user_indexes` (feature-040 observability SQL) with debug-run metrics.
- Authn/authz for the admin route if the tool is exposed beyond local/dev.

## Learnings (carried from features 038–040)

- Semantic ≠ keyword: a query mentioning an exact term (e.g. `SAML`, `RFC 6749`) can rank semantically-related but lexically-absent chunks highly — exactly the case this screen must make visible via the lexical branch and diff.
- Duplicate ingests (`source_path`) produce identical embeddings/distances and can occupy multiple slots; the diff view should make this obvious.
- Cosine distance interpretation: ~0.2–0.4 strong, ~0.65+ moderate on the small course corpus; the normalized `score` and explanation must not overstate weak matches.
- Operators should inspect score magnitude, not only rank — a core teaching goal of this screen.

## Estimation

- Size: L epic, split into 7 sub-features (042–048; 048 optional).
- Suggested order: 042 → 043 → 044 → 045 → 046 → 047, with 048 any time after 043.
- Each sub-feature is independently shippable and verifiable.

## Repository commits (master-ia)

| Commit | Summary |
| --- | --- |
| `d638ed9` | Close the final retrieval debug screen and epic acceptance gaps: inspector matched terms, full tuning/filter controls, zero-result warnings, verification evidence, and synchronized docs. |
