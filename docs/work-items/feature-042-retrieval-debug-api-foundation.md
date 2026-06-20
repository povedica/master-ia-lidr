# Feature: Retrieval Debug API Foundation (Vector Branch + Chunk Inspector)

> Sub-feature 1 of 7 of the epic `feature-041-retrieval-debug-observability-screen`.
> Depends on: features 036–040 (existing pgvector semantic search). No dependency on other 04x sub-features.
> Internal tooling. Not user-facing.

## Why this sub-feature

Today retrieval is a black box: `POST /api/v1/search` returns a flat list with a raw cosine `distance` and nothing that explains *why* a chunk appeared, *where* it ranked, or *what* the chunk's surrounding context is. Before adding new strategies (lexical, hybrid, rerank) we need a stable, debug-only API contract that exposes retrieval as structured, explainable data. Establishing this contract first lets every later sub-feature plug a new branch into the same response shape without re-litigating the API.

## Objective

Deliver an additive, internal debug API that runs the **vector branch** (reusing the existing cosine-distance path) and returns a rich, explainable trace per result, plus a chunk-inspection endpoint for deep context. No new retrieval strategy is introduced here; the value is observability of what already exists.

## Value increment (what ships and why it matters)

- A working `POST /api/v1/retrieval-debug` that, for `strategies: ["vector"]`, returns per-result rank, raw `distance`, normalized `score`, `source_strategies`, metadata, timings, and a (single-branch) explanation.
- A working `GET /api/v1/retrieval-debug/chunks/{id}` for full content, neighbor context, full metadata, and embedding model.
- The canonical request/response **schemas** and **branch container** that sub-features 043–046 extend.
- Result: an operator (via curl/Swagger) can already diagnose vector retrieval relevance before any UI exists.

## SMART framing

- **Specific:** two endpoints, one branch (vector), fixed response schema.
- **Measurable:** acceptance criteria AC-01…AC-12 below; default test suite green without real keys/DB.
- **Achievable:** reuses `OpenAIEmbedder.embed_one()` and `SemanticSearchRepository`; no new infra.
- **Relevant:** unblocks every other sub-feature by fixing the contract.
- **Time-boxed:** Size M, ~6 baby steps.

## Context

- Reuse `app/embedding_pipeline/search.py:run_semantic_search` / `SemanticSearchRepository.build_search_statement()` (cosine distance, `embedding IS NOT NULL`, order asc, limit k). Do **not** modify `POST /api/v1/search`.
- Embedding via `OpenAIEmbedder.embed_one()`, model `EMBEDDING_PIPELINE_MODEL` (`text-embedding-3-small`, 1536).
- Models `Document` (`source_path`, `document_type`, `metadata_`) and `Chunk` (`document_id`, `chunk_type`, `content`, `embedding`, `metadata_`).
- DB endpoints depend on `get_db_session`; empty `DATABASE_URL` → safe `503`.
- See `feature-041` for the full shared design (response example, explanation vocabulary, telemetry keys).

## Scope

### Includes

- `app/embedding_pipeline/retrieval_debug_schemas.py`: `RetrievalDebugRequest`, `BranchResultEntry`, `DebugResult`, `ResultExplanation`, `RetrievalDebugResponse`, `ChunkInspectionResponse`. The `branches` container keys are nullable per strategy so future branches slot in.
- `app/embedding_pipeline/retrieval_debug.py`: orchestrator that, for the vector branch, embeds the query once, runs the search, normalizes `score = 1 - distance`, applies optional semantic `threshold`, builds the per-result trace and a single-branch explanation, assembles `timings_ms` and `warnings`.
- A vector branch adapter that exposes `rank`, `distance`, and normalized `score` from the existing repository without changing `/search`.
- `app/routers/retrieval_debug.py`: `POST /retrieval-debug` and `GET /retrieval-debug/chunks/{id}`; registered under `/api/v1` in `app/main.py`.
- Chunk inspector: full content, previous/next chunk by id within the document, parent `Document` reference, full metadata, `embedding_model`, `embedding_present`, `chunk_type`; optional `?query=` → cosine distance/similarity for that chunk.
- Structured telemetry skeleton: `retrieval_debug_completed` log with safe keys.
- Deterministic tests (mocked embedder, seeded vector rows / mocked session).
- README + technical docs for the new debug API.

### Excludes

- Lexical, hybrid, rerank branches (043/044/045).
- Metadata filters (046) and the React screen (047).
- Any change to `POST /api/v1/search`.
- Persistence/export of debug runs.
- Real OpenAI calls in default tests.

## Functional Requirements

### FR-01 — Request

```text
POST /api/v1/retrieval-debug
```

```json
{
  "query": "JWT refresh token rotation for OAuth2 REST API",
  "strategies": ["vector"],
  "vector": { "top_k": 20, "threshold": null },
  "max_results": 15
}
```

Validation: `query` non-empty trimmed; `strategies` non-empty subset of supported branches or `"all"` (only `vector` active in this sub-feature; other requested-but-unimplemented branches return `null` with a `warnings` note); `top_k` 1–50; `max_results` 1–50; `threshold` optional float in documented range. Invalid → `422`.

### FR-02 — Response (vector-only shape)

- `query`, `applied_config`, `timings_ms` (`vector`, `total`), `warnings`.
- `branches.vector`: list of `{ rank, chunk_id, document_id, score, distance }`; other branch keys `null`.
- `final_results`: ordered by vector rank (post-threshold, capped at `max_results`), each with `final_position`, `chunk_id`, `document_id`, `title` (derived from metadata e.g. `budget_id` + component, fallback `source_path`), `content_excerpt`, `semantic_score`, `semantic_rank`, `semantic_distance`, `source_strategies: ["vector"]`, `metadata`, `explanation` (`summary` + `signals` from the controlled vocabulary, e.g. `semantic_strong`/`semantic_weak`/`below_threshold`).
- Empty corpus → `200` with empty `branches.vector` and `final_results`.

### FR-03 — Chunk inspection

```text
GET /api/v1/retrieval-debug/chunks/{chunk_id}?query=<optional>
```

Returns full `content`, `previous_chunk`/`next_chunk` (by id within `document_id`), parent `document` (`source_path`, `document_type`, metadata), full chunk `metadata`, `embedding_model`, `embedding_present`, `chunk_type`; when `query` provided, `distance` and `similarity`. Unknown id → `404`.

### FR-04 — Safety & telemetry

- Empty `DATABASE_URL` → `503`; provider/DB errors → safe error, no stack traces/secrets.
- Log `retrieval_debug_completed` with `request_id`, `strategies`, vector result count, `timings_ms`, `max_results`. No embeddings/keys.

## Technical Approach

- Reuse `run_semantic_search` internals or call the repository directly to obtain ordered `(chunk, distance)`; derive `rank` (1-based) and `score = 1 - distance` clamped to `[0,1]`.
- Threshold: drop results whose similarity `< threshold` (or `distance > 1 - threshold`); document the exact convention.
- Explanation builder is a pure function `build_explanation(branch_signals) -> ResultExplanation`; for vector-only it emits `semantic_strong` (e.g. distance ≤ 0.4), `semantic_weak`, or `below_threshold`.
- Router orchestrates; the service owns logic; the embedder/SDK is never called from the handler.

## Acceptance Criteria

- [ ] AC-01: `POST /api/v1/retrieval-debug` and `GET /api/v1/retrieval-debug/chunks/{id}` appear in OpenAPI under `/api/v1`.
- [ ] AC-02: `strategies: ["vector"]` returns `200` with `branches.vector`, `final_results`, `timings_ms`, `warnings`; non-vector branch keys are `null`.
- [ ] AC-03: The embedder is called exactly once per debug request; vector ranking matches the existing cosine-distance order.
- [ ] AC-04: Each `final_results` item includes final position, chunk id, document id, title, excerpt, `semantic_score`, `semantic_rank`, `semantic_distance`, `source_strategies`, metadata, and a structured `explanation`.
- [ ] AC-05: `threshold` drops weak hits; dropped chunks carry the `below_threshold` signal where surfaced; `max_results` caps the list.
- [ ] AC-06: Requesting an unimplemented branch (e.g. `lexical`) yields a `warnings` entry and `null` branch, not an error.
- [ ] AC-07: Empty corpus → `200` empty results; invalid input → `422`; empty `DATABASE_URL` → `503`.
- [ ] AC-08: `GET /retrieval-debug/chunks/{id}` returns content, neighbor context, parent document, full metadata, embedding model, chunk type; `?query=` adds distance/similarity; unknown id → `404`.
- [ ] AC-09: `POST /api/v1/search` behavior and schema are unchanged (regression test green).
- [ ] AC-10: `retrieval_debug_completed` log emitted with safe keys only.
- [ ] AC-11: Default suite passes without real API keys or live Postgres.
- [ ] AC-12: README + technical docs document the debug API contract and how to read `distance`/`score`.

## Test Plan

- Unit: request validation (bounds, strategies subset); explanation builder signals; title derivation; threshold filtering.
- Service: fake embedder + seeded rows → assert ranks, normalized scores, capped results, warnings for unimplemented branch.
- Repository/router: vector adapter does not change `/search`; OpenAPI routes exist; `200/422/503/404` paths; chunk inspector neighbor logic with mocked session.
- Manual: Compose Postgres + ingested corpus → curl debug + chunk inspector.

## Verification

- Automated: `uv run pytest tests/embedding_pipeline -q` (157 passed, 2 deselected).
- Manual: curl `POST /api/v1/retrieval-debug` and `GET /retrieval-debug/chunks/{id}` on Compose Postgres.
- Not verified: manual curl on live Compose Postgres; lexical/hybrid/rerank branches are intentionally later sub-features.

## Documentation Plan

- [x] `README.md`: internal-tools subsection with the debug API + curl example + note it is internal-only.
- [x] `docs/technical/README.md`: schemas, normalization, explanation vocabulary, telemetry keys.
- [x] `docs/arquitectura-estimador-cag.html`: API surface, router tree, embedding pipeline flow, endpoint table.
- [x] Second Brain: short learning note on making vector retrieval observable.

## Implementation Plan

- [ ] Step 1: `retrieval_debug_schemas.py` + validation tests (RED→GREEN).
- [ ] Step 2: Vector branch adapter (rank + normalized score) + tests; assert `/search` unchanged.
- [ ] Step 3: Explanation builder (vector signals) + threshold filtering + unit tests.
- [ ] Step 4: `retrieval_debug.py` orchestrator (single branch, timings, warnings) + service tests.
- [ ] Step 5: Router + `main.py` registration + chunk inspector + router tests (200/422/503/404).
- [ ] Step 6: Telemetry log + docs sweep.

## Estimation

- Size: M
- Estimated time: 3 hours
- Planned steps: 6
- Notes: Unblocks 043–047.

## Implementation progress

- [x] Setup: branch, draft PR, and WIP label.
- [x] Step 1: Debug schemas and validation.
- [x] Step 2: Vector branch adapter with rank and normalized score.
- [x] Step 3: Explanation builder and threshold filtering.
- [x] Step 4: Retrieval debug orchestrator.
- [x] Step 5: Router registration and chunk inspector.
- [x] Step 6: Telemetry, documentation, and final verification.

## Pull request

- Draft PR: https://github.com/povedica/master-ia-lidr/pull/37

## Repository commits (master-ia)

| Commit | Summary |
|--------|---------|
| `4ff4c21` | Added the canonical feature work item, estimation, and implementation progress tracker. |
| `014a570` | Recorded draft PR tracking in the canonical work item. |
| `3c10415` | Added retrieval debug request/response schemas and validation tests. |
| `bdf97b2` | Added vector branch entries with rank, raw distance, and normalized score. |
| `df1a527` | Added vector explanation signals and threshold filtering. |
| `abe82fd` | Added the retrieval debug orchestrator for vector traces and warnings. |
| `2120149` | Exposed retrieval debug HTTP endpoints and chunk inspector with router tests. |
