# Feature: Retrieval Metadata Filters Across Branches

> Sub-feature 5 of 7 of the epic `feature-041-retrieval-debug-observability-screen`.
> Depends on: `feature-042` (debug API + branch queries). Best sequenced after `feature-043`/`feature-044` so all branches honor filters, but technically only requires 042.
> Internal tooling. Not user-facing.

## Why this sub-feature

Diagnosing relevance often requires scoping the corpus: "only finance sector", "only 2023–2025", "only chunks tagged python". Without filters, operators can't isolate variables when tuning, and the diff/explanation views are noisier than necessary. The GIN index on `chunks.metadata` already exists (`ix_chunks_metadata_gin`) but search ignores it. This sub-feature turns existing metadata into an actionable scoping control.

## Objective

Add metadata filtering at the repository level for the vector and lexical branches (and therefore hybrid candidates), driven by a `filters` object in the debug request, using the existing JSONB metadata and `Document` fields. Unknown/empty filters are ignored without error.

## Value increment (what ships and why it matters)

- `POST /api/v1/retrieval-debug` accepts `filters` (document type, sector, technology, year range, source, tags, language) applied to every branch's candidate set.
- Operators can isolate retrieval behavior to a controlled subset, making diff/explanation diagnosis precise.
- The filter `WHERE` logic is shared and reused by all branches, leveraging the existing GIN index.

## SMART framing

- **Specific:** one shared filter clause builder applied to vector + lexical repositories.
- **Measurable:** AC-01…AC-09; filters narrow candidates; unknown keys ignored; `/search` unchanged.
- **Achievable:** JSONB containment + range predicates on existing columns; index already present.
- **Relevant:** precision/isolation for tuning, a core epic goal.
- **Time-boxed:** Size S–M, ~4 baby steps.

## Context

- `Chunk.metadata_` (JSONB) carries `client_sector`, `main_technology`, `year`, `source_name`, etc. `Document.document_type` and `Document.metadata_` carry document-level attributes.
- GIN index `ix_chunks_metadata_gin` supports JSONB containment (`@>`) efficiently.
- `tags`/`language` may or may not exist in current metadata; filters on absent keys must simply match nothing or be ignored per documented rule (decide and document: ignore-if-empty, AND-combine provided filters).

## Scope

### Includes

- A shared filter spec model in `retrieval_debug_schemas.py`: `filters` = `{ document_type?, client_sector?, main_technology?, source_name?, language?, tags?: string[], year?: { from?, to? } }`.
- A pure clause builder `build_metadata_filters(filters) -> list[ColumnElement]` producing SQLAlchemy predicates:
  - JSONB equality/containment for scalar keys (`metadata @> '{"client_sector": "finance"}'`).
  - `tags` as JSONB array containment (`metadata->'tags' @> '["python"]'` or `?|` semantics — documented).
  - `year` range via JSONB numeric cast or document column.
  - `document_type` via join/lookup against `documents` when needed.
- Apply filters in `SemanticSearchRepository` (debug path only) and `LexicalSearchRepository` without changing production `POST /api/v1/search`.
- Validation: empty/unknown keys ignored; provided filters AND-combined.
- Unit (clause builder) + repository + service tests; docs.

### Excludes

- Faceting/aggregations or filter auto-suggestions (future).
- New indexes beyond the existing GIN (no schema change).
- Frontend filter UI (047 consumes this contract).
- Changing `/search`.

## Functional Requirements

### FR-01 — Filter request

`filters` is optional; each key optional. Provided keys are AND-combined. Empty object or `null` → no filtering. Unknown keys → ignored (documented), not `422` (but malformed types, e.g. `year.from` non-integer, → `422`).

### FR-02 — Applied to all branches

When filters are present, vector and lexical branches both restrict candidates before ranking/limiting; hybrid therefore fuses only filtered candidates. The `applied_config` echoes the normalized filters.

### FR-03 — Behavior

- Filters that match nothing → branches return empty (valid `200`).
- `year.from`/`year.to` inclusive range; either bound optional.
- `tags` matches chunks containing all (documented) requested tags.

## Technical Approach

- `build_metadata_filters` is pure and unit-tested by compiling predicates / asserting SQL text with a dialect.
- Use JSONB `@>` containment to leverage `ix_chunks_metadata_gin`; document chosen `tags` semantics (contains-all vs any).
- Keep the debug repositories' filtered statements separate from the production `/search` statement (e.g. an optional `filters` parameter defaulting to none).

## Acceptance Criteria

- [x] AC-01: `filters` model validates types (e.g. `year` ints) and ignores empty/unknown keys; malformed types → `422`.
- [x] AC-02: `build_metadata_filters` emits correct predicates for scalar keys via JSONB containment.
- [x] AC-03: `tags` filter uses documented JSONB array semantics; `year` range is inclusive with optional bounds.
- [x] AC-04: Vector branch restricts candidates to matching chunks (repository test).
- [x] AC-05: Lexical branch restricts candidates to matching chunks (repository test).
- [x] AC-06: Hybrid fuses only filtered candidates; `applied_config` echoes normalized filters.
- [x] AC-07: Filters matching nothing → `200` with empty branches; no error.
- [x] AC-08: `POST /api/v1/search` query/behavior unchanged (regression test).
- [x] AC-09: Default suite passes offline; docs explain filter keys, `tags`/`year` semantics, and GIN index usage.

## Test Plan

- Unit: clause builder per key + combinations + empty/unknown handling.
- Repository: vector + lexical filtered statements compile and narrow rows (mocked session / dialect compile).
- Service: end-to-end debug run with filters across branches; empty-match path; `applied_config` echo.
- Manual: Compose Postgres — same query with/without filters; confirm narrowed branches + `EXPLAIN` shows GIN usage where applicable.

## Verification

- Verified: `uv run pytest tests/embedding_pipeline/test_retrieval_debug_schemas.py -q` (`29 passed`).
- Verified: `uv run pytest tests/embedding_pipeline/test_retrieval_metadata_filters.py -q` (`5 passed`).
- Verified: `uv run pytest tests/embedding_pipeline/test_search_repository.py tests/embedding_pipeline/test_lexical_search_repository.py -q` (`8 passed`).
- Verified: `uv run pytest tests/embedding_pipeline/test_retrieval_debug_service.py tests/embedding_pipeline/test_retrieval_debug_router.py -q` (`19 passed`).
- Verified: `uv run pytest tests/embedding_pipeline/test_search_router.py -q` (`6 passed`).
- Verified: `uv run pytest tests/embedding_pipeline -q` (`200 passed, 2 deselected`).
- Verified: `ReadLints` found no linter errors in edited Python files.
- Not verified: manual Compose Postgres curl/`EXPLAIN` with a live corpus.
- Residual risk: large-corpus planner behavior for `year` casts and `document_type` joins still needs live Postgres inspection; faceting remains out of scope.

## Documentation Plan

- [x] `docs/technical/README.md`: filter contract, JSONB containment, `tags`/`year` semantics, GIN index reuse.
- [x] `README.md`: filter example in internal-tools section.
- [x] `docs/arquitectura-estimador-cag.html`: retrieval debug flow and module table updated for metadata filters.
- [x] `learnings/aprendizajes/retrieval-metadata-filters-debug.md`: note on isolating variables for relevance tuning.

## Pull Request

- Draft PR: https://github.com/povedica/master-ia-lidr/pull/42

## Implementation Plan

- [ ] Step 1: `filters` schema + validation tests (RED→GREEN).
- [ ] Step 2: `build_metadata_filters` pure builder + unit tests.
- [ ] Step 3: Apply filters in vector + lexical repositories (debug path) + repository tests; assert `/search` unchanged.
- [ ] Step 4: Service end-to-end + docs sweep + manual verification.

## Estimation

- Size: M
- Estimated time: 3 hours
- Planned steps: 5
- Depends on 042 (and ideally 043/044); feeds 047 filter UI.

## Implementation progress

- [x] Step 1: Filter schema and validation tests.
- [x] Step 2: Pure SQLAlchemy metadata filter builder and unit tests.
- [x] Step 3: Apply filters in vector and lexical repositories.
- [x] Step 4: Wire filters through retrieval debug orchestration and API contract.
- [x] Step 5: Documentation, handoff, and final verification.

## Handoff from feature-046

Shipped interfaces:

- `RetrievalDebugRequest.filters` accepts optional `document_type`, `client_sector`, `main_technology`, `source_name`, `language`, `tags`, and `year.from` / `year.to`.
- `SemanticSearchRepository.search_chunks()` and `LexicalSearchRepository.search_chunks()` accept optional `filters` for debug callers; default `None` preserves existing `/api/v1/search` behavior.
- `build_metadata_filters(filters)` centralizes SQLAlchemy predicates for JSONB scalar containment, tags contains-all, inclusive year bounds, and document type equality.
- `applied_config.filters` echoes normalized filters when present.

Changed contracts:

- Unknown filter keys are ignored.
- Empty filter objects normalize to no filtering.
- Malformed typed values still return validation errors.
- Filters are AND-combined before branch ranking and limiting; hybrid only sees filtered branch candidates.

Verification evidence:

- `uv run pytest tests/embedding_pipeline -q` passed with `200 passed, 2 deselected`.
- Lints reported no errors for edited Python files.

Not verified:

- Live Compose Postgres curl checks with an ingested corpus.
- `EXPLAIN` confirmation for GIN usage and planner behavior on larger corpora.

Residual risks:

- JSONB scalar containment can use `ix_chunks_metadata_gin`, but `year` casts and `document_type` joins may require future typed/generated indexes if the corpus grows.
- `tags` requires contains-all; frontend feature 047 should expose that clearly.

Recommended first tests for feature-047:

- Send `filters` from the internal debug screen and assert `applied_config.filters` mirrors normalized values.
- Exercise empty-match responses and verify the UI renders empty branches without treating them as errors.
- Make `tags` copy explicit as "contains all selected tags".

## Repository commits (master-ia)

| Commit | Summary |
| --- | --- |
| `cc3e016` | Track the feature work item, initial estimation, and implementation progress for metadata filters. |
| `7edd31b` | Add and verify the retrieval debug metadata filter request schema. |
| `fac1723` | Add shared SQLAlchemy predicates for retrieval debug metadata filters. |
| `46903f1` | Apply retrieval metadata filters in vector and lexical repository statements. |
| `0551ee5` | Wire metadata filters through retrieval debug orchestration and API responses. |
| `606ab6d` | Document retrieval debug metadata filters, verification, and handoff. |
