# Feature: Hybrid Fusion + Ranking Diff + Explanation Engine

> Sub-feature 3 of 7 of the epic `feature-041-retrieval-debug-observability-screen`.
> Depends on: `feature-042` (debug API) and `feature-043` (lexical branch).
> Internal tooling. Not user-facing.

## Why this sub-feature

Once two independent rankings exist (vector + lexical), the real diagnostic value appears in *combining and comparing* them. Operators need to see how a fused ranking is built, which results both branches agree on (consensus), which are exclusive to one branch, which were rescued by hybridization, and which moved a lot. This sub-feature turns two separate lists into a single explainable, comparable picture — the analytical core of the epic.

## Objective

Add configurable **rank fusion** (Reciprocal Rank Fusion by default, optional weighted), a **ranking diff** across branches, and a full **explanation engine** with a controlled signal vocabulary, exposed through the existing debug API as `branches.hybrid`, `diff`, and richer `final_results[].explanation`.

## Value increment (what ships and why it matters)

- `strategies` including `hybrid` produces a fused ranking with a transparent score.
- `diff` reports common / vector-only / lexical-only / hybrid-rescued / big-movers / dropped sets.
- Each `final_result` gets a human-readable explanation plus structured `signals` (`branch_consensus`, `hybrid_rescued`, `semantic_strong`, `lexical_exact_match`, …).
- Result: an operator can answer "why is this #1, and why did that drop?" directly from the response.

## SMART framing

- **Specific:** pure fusion module + diff builder + explanation engine + hybrid branch wiring.
- **Measurable:** AC-01…AC-12; deterministic unit tests for fusion/diff/explanation.
- **Achievable:** pure functions over existing branch outputs; no new I/O.
- **Relevant:** delivers consensus/divergence analysis, the epic's analytical core.
- **Time-boxed:** Size M, ~6 baby steps.

## Context

- Inputs are the per-branch rankings produced by `feature-042` (vector) and `feature-043` (lexical).
- Response already reserves `branches.hybrid`, `diff`, and `final_results[].explanation` fields (extend schemas if needed).
- Fusion and diff must be deterministic and side-effect free for testability.

## Handoff from feature-043

Feature-043 shipped the lexical full-text branch on branch `feature/043-lexical-fulltext-search-branch` and PR `#39`. The next implementation should build on these concrete pieces:

- `POST /api/v1/retrieval-debug` now implements `vector` and `lexical`; `hybrid` and `rerank` remain future strategies that return `null` with warnings when requested.
- `LexicalSearchRepository` lives in `app/embedding_pipeline/lexical_search_repository.py` and exposes `search_chunks(session, query, top_k)` plus `build_search_statement()`. It uses Postgres `websearch_to_tsquery`, on-the-fly `to_tsvector('english', chunks.content)`, `ts_rank_cd`, `ts_headline`, and branch-local row mapping to `LexicalSearchResult`.
- `BranchResultEntry` now supports `distance: float | None` and `matched_terms: list[str]`, so lexical entries can omit vector distance while preserving exact-term evidence.
- `DebugResult` now supports nullable semantic fields plus `lexical_score`, `lexical_rank`, and `matched_terms`; lexical-only requests can return final results without semantic fields.
- `run_retrieval_debug()` accepts an injectable `lexical_repository`, runs vector and lexical branches via `asyncio.gather(..., return_exceptions=True)`, and returns partial results with warnings if one branch fails.
- Vector final results are enriched with lexical evidence when the same chunk appears in both branches; `source_strategies` becomes `["vector", "lexical"]` in that case.
- Lexical score normalization is implemented in `build_lexical_branch_entries()`: min-max over branch-local `ts_rank_cd`, with all-equal ranks normalized to `1.0`.
- Explanation helpers currently emit vector signals (`semantic_strong`, `semantic_weak`, `below_threshold`) and lexical signal `lexical_exact_match`; feature-044 should replace or centralize this into the full explanation engine rather than layering a second ad hoc signal builder.
- Safe completion logging includes `vector_result_count`, `lexical_result_count`, `timings_ms`, and `max_results`; it still does not log query text, chunk content, embeddings, or secrets.
- Documentation already describes the lexical sequential-scan baseline and defers indexed FTS / `pg_trgm` to `feature-048`.

Verification carried from feature-043:

- `uv run pytest tests/embedding_pipeline -q` (`170 passed, 2 deselected`).
- `uv run pytest` (`561 passed, 11 skipped, 12 deselected`).

Not verified in feature-043:

- Live Compose/Postgres curl smoke for `strategies: ["lexical"]` and `"all"`.
- Fusion/diff behavior and indexed lexical performance remain out of scope.

Recommended first tests for feature-044:

- `tests/embedding_pipeline/test_fusion.py`: RRF ranking, weighted ranking, weight normalization, and deterministic tie-breaking.
- `tests/embedding_pipeline/test_retrieval_debug_service.py`: `strategies: ["vector", "lexical", "hybrid"]` returns `branches.hybrid`, fused final ordering, and enriched fields from both input branches.
- `tests/embedding_pipeline/test_retrieval_debug_schemas.py`: hybrid config validation and new nullable `fusion_score`, `fusion_rank`, and `diff` response fields.

## Scope

### Includes

- `app/embedding_pipeline/fusion.py`:
  - `reciprocal_rank_fusion(branch_rankings, *, k=60, weights=None) -> list[FusedEntry]`
  - `weighted_fusion(branch_rankings, *, weights) -> list[FusedEntry]`
  - weight normalization; deterministic tie-breaking (e.g. by chunk_id).
- Diff builder (`build_ranking_diff(branches, final, *, threshold_drops, rerank_drops=None) -> RankingDiff`): common, `vector_only`, `lexical_only`, `hybrid_rescued`, `big_movers` (rank delta beyond a documented threshold), `dropped_by_threshold`, `dropped_by_rerank` (empty until 045).
- Explanation engine (`build_explanation(...)`) producing `summary` (technical English) + `signals` from the controlled vocabulary: `semantic_strong`, `semantic_weak`, `lexical_exact_match`, `branch_consensus`, `hybrid_rescued`, `below_threshold` (plus `rerank_*` reserved for 045).
- Hybrid branch wiring in `retrieval_debug.py`: build `branches.hybrid`, compute `fusion_score`/`fusion_rank` on `final_results`, set final ordering from the fused list, attach `diff` and explanations, honor `hybrid.enabled=false` (omit hybrid; final order falls back to the requested single branch or documented default).
- Config: `hybrid` = `{ enabled, method: "rrf"|"weighted", rrf_k, weights: { vector, lexical } }`; weighted requires weights else `422`.
- Unit + service tests; docs.

### Excludes

- Rerank (045) — `dropped_by_rerank` stays empty; `rerank_*` signals unused here.
- Metadata filters (046), frontend (047), indexed FTS (048).

## Functional Requirements

### FR-01 — Fusion config & behavior

- Default `method="rrf"`, `rrf_k=60`, equal weights.
- `method="weighted"` combines per-branch normalized scores by provided weights (normalized server-side).
- `hybrid.enabled=false` → no `branches.hybrid`; `final_results` ordered by the single requested branch (or documented precedence when multiple non-hybrid branches requested).

### FR-02 — Final ordering & trace

When hybrid is enabled, `final_results` are ordered by `fusion_rank`, capped at `max_results`, each carrying `semantic_*`, `lexical_*`, `fusion_score`, `fusion_rank`, `source_strategies`, and `explanation`.

### FR-03 — Diff

`diff` is consistent with branch rankings: `common` (in ≥2 branches), `*_only` (exclusive), `hybrid_rescued` (low/absent in a single branch but lifted into top final by fusion), `big_movers` (rank delta ≥ documented threshold between a branch and the fused list), `dropped_by_threshold` (removed by semantic threshold from 042).

### FR-04 — Explanation

Every `final_result` has a deterministic `explanation.summary` and a `signals` list drawn only from the controlled vocabulary; signals must reflect the actual branch evidence (e.g. present in both branches → `branch_consensus`).

## Technical Approach

- `fusion.py` is pure (no DB/HTTP); RRF: `score = Σ_branch weight_b / (k + rank_b)`.
- Diff and explanation are pure functions over branch rankings + final list; isolate thresholds as documented constants/config.
- Orchestrator composes: gather branches (042/043) → fuse → order → diff → explain → assemble timings (`hybrid` timing ~0–few ms) + warnings.

## Acceptance Criteria

- [ ] AC-01: `reciprocal_rank_fusion` ranks by `Σ weight/(k+rank)`; `rrf_k` and `weights` change order as expected; ties broken deterministically.
- [ ] AC-02: `weighted_fusion` combines normalized branch scores by normalized weights; missing weights with `method="weighted"` → `422`.
- [ ] AC-03: `strategies` incl. `hybrid` returns `branches.hybrid` with `{rank, chunk_id, document_id, score}`.
- [ ] AC-04: `final_results` ordered by `fusion_rank`, capped at `max_results`, with `fusion_score`/`fusion_rank` populated.
- [ ] AC-05: `hybrid.enabled=false` omits the hybrid branch and falls back to the documented single-branch order.
- [ ] AC-06: `diff.common` lists chunks in ≥2 branches; `vector_only`/`lexical_only` are exclusive sets.
- [ ] AC-07: `diff.hybrid_rescued` identifies chunks lifted into top final by fusion despite weak single-branch rank.
- [ ] AC-08: `diff.big_movers` reports rank deltas beyond the documented threshold with `from_rank`/`to_rank`/`delta`.
- [ ] AC-09: `diff.dropped_by_threshold` reflects 042 threshold removals; `dropped_by_rerank` is empty.
- [ ] AC-10: Each `final_result.explanation` has a summary + controlled-vocabulary `signals` consistent with branch evidence (consensus, rescue, strong/weak, exact-match).
- [ ] AC-11: Fusion/diff/explanation are deterministic (same input → same output) and covered by unit tests.
- [ ] AC-12: Default suite passes offline; docs explain RRF math, weighted fusion, diff sets, and the signal vocabulary.

## Test Plan

- Unit: RRF ordering + `rrf_k`/weights effects + ties; weighted fusion + weight normalization; diff sets from synthetic rankings; explanation signals from crafted branch evidence.
- Service: vector+lexical → hybrid end-to-end with fakes; `enabled=false` fallback; `max_results` cap; diff/explanation attached.
- Manual: Compose query mixing semantics + exact terms; verify rescued/consensus/movers match intuition.

## Verification

- Automated: `uv run pytest tests/embedding_pipeline -q`.
- Manual: curl debug `strategies: "all"`, toggle `rrf_k`/weights/`enabled`; inspect `diff` + explanations.
- Not verified yet: rerank reordering (045).

## Documentation Plan

- `docs/technical/README.md`: fusion math (RRF + weighted), diff definitions, signal vocabulary, thresholds.
- `README.md`: hybrid example in internal-tools section.
- Second Brain: note on what fusion/diff reveal about semantic vs lexical trade-offs.

## Implementation Plan

- [ ] Step 1: `fusion.py` (RRF + weighted) + pure unit tests.
- [ ] Step 2: Diff builder + unit tests.
- [ ] Step 3: Explanation engine + unit tests.
- [ ] Step 4: Wire hybrid branch + final ordering + `fusion_*` fields into `retrieval_debug.py` + service tests.
- [ ] Step 5: Attach `diff` + explanations to response; `enabled=false` fallback; validation for weighted method.
- [ ] Step 6: Docs sweep + manual verification.

## Estimation

- Size: M
- Estimated time: 3 hours
- Planned steps: 6
- Depends on: 042, 043
- Unblocks: 045, 047

## Implementation progress

- [ ] Step 1: Fusion core.
- [ ] Step 2: Ranking diff builder.
- [ ] Step 3: Explanation engine.
- [ ] Step 4: Hybrid schemas and config.
- [ ] Step 5: Hybrid service wiring.
- [ ] Step 6: Documentation and full validation.
