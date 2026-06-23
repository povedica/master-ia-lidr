# Feature: Retrieval Evaluation Evidence and Recommendation

## Objective

Complete the remaining evidence work for the hybrid retrieval exercise by running the existing A/B/C/D retrieval modes against the golden set on a populated corpus, producing reproducible evaluation artifacts, and writing a concise recommendation that explains the precision/latency trade-off.

This feature does not redesign retrieval. It closes the quality gap left after `feature-050`: the implementation exists, but the real evaluation artifacts and final conclusion are not present under `evaluation/retrieval/results/`.

## Context

The exercise asks for:

- PostgreSQL full-text search over Spanish budget content using a generated `tsvector` column and GIN index.
- Hybrid search through vector + lexical Reciprocal Rank Fusion.
- Optional cross-encoder reranking with recall-then-rerank (`top-50` recall, final `top-5`).
- A golden set of 5 project-estimation queries.
- Measurement of four modes:
  - A: vector search, no rerank.
  - B: hybrid search, no rerank.
  - C: vector search, rerank.
  - D: hybrid search, rerank.
- A comparison table with precision@5 and latency.
- A final conclusion on which configuration to use and whether reranking justifies its latency.

Existing shipped pieces from `feature-050`:

- `alembic/versions/0004_set_chunks_content_tsv_spanish.py` regenerates `chunks.content_tsv` with `to_tsvector('spanish', content)` and recreates the GIN index.
- `app/embedding_pipeline/lexical_search_repository.py` uses configurable PostgreSQL FTS, defaulting to `spanish`.
- `app/embedding_pipeline/fusion.py` provides `reciprocal_rank_fusion`.
- `app/embedding_pipeline/retrieval_service.py` exposes modes A/B/C/D.
- `app/embedding_pipeline/rerank.py` provides `CrossEncoderReranker` and `build_reranker`.
- `app/scripts/retrieval_eval.py` can run the evaluation and emit `results.json`, `comparison.md`, and `recommendation.md`.
- `evaluation/retrieval/golden_set.json` contains 5 labeled queries.

Current gap:

- No files exist under `evaluation/retrieval/results/**`.
- The golden-set labels have not been reviewed as domain labels.
- Real cross-encoder relevance and latency have not been measured on the populated corpus.
- The final recommendation has not been written from actual numbers.

## Scope

### Includes

- Review `evaluation/retrieval/golden_set.json` for domain relevance and adjust labels only when the current corpus proves the existing labels are incorrect or unavailable.
- Verify the local evaluation prerequisites: populated PostgreSQL database, Alembic at head, embeddings present, `budget_id` metadata available, and reranker configured as non-noop.
- Run all four retrieval modes A/B/C/D with fixed settings: `RETRIEVAL_RECALL_K=50`, `RETRIEVAL_TOP_K_FINAL=5`, and a documented `RETRIEVAL_RRF_K`.
- Produce one timestamped results directory under `evaluation/retrieval/results/<timestamp>/`.
- Commit the generated `results.json`, `comparison.md`, and `recommendation.md` when they contain no secrets or sensitive local-only values.
- Update documentation or the work item with the exact commands, environment assumptions, selected reranker model, corpus snapshot notes, and residual risks.
- Add small validation or harness hardening only if required to prevent misleading results, such as detecting empty corpus, missing `budget_id`, missing embeddings, or accidental no-op reranker.

### Excludes

- Rewriting `RetrievalService`, `LexicalSearchRepository`, RRF, or the reranker architecture unless a blocking correctness bug is found during validation.
- Adding new retrieval modes beyond A/B/C/D.
- Changing the estimation generation pipeline to consume the recommended retrieval mode.
- Expanding the golden set beyond 5 queries.
- Real API keys, local `.env` values, or provider secrets in committed files.
- Treating the 5-query evaluation as statistically significant; it is directional evidence for the exercise.

## Functional Requirements

### FR-01 — Evaluation Preflight

Before running the final evaluation, the task must verify that:

- `DATABASE_URL` points to the intended local evaluation database.
- Alembic is at head and includes migration `0004`.
- The `chunks` table has rows with non-null `embedding`, generated `content_tsv`, and `metadata->budget_id`.
- `RETRIEVAL_RERANK_ENABLED=true`.
- `RETRIEVAL_RERANK_MODEL` is non-empty and `build_reranker(settings).is_noop` is `False`.
- The selected reranker model and runtime are documented.

If any preflight condition fails, the run must stop with a clear note instead of producing misleading zero metrics.

### FR-02 — Golden Set Review

The golden set remains exactly 5 queries unless a label is demonstrably invalid for the current corpus. For each query:

- Confirm that every `relevant_budget_ids` entry exists in the current corpus metadata.
- Confirm the label represents a good estimation analogue, not just topical similarity.
- Preserve or update `notes` so the relevance rationale is auditable.

### FR-03 — Reproducible Run

The final run must use one documented command, for example:

```bash
RETRIEVAL_RERANK_ENABLED=true \
RETRIEVAL_RERANK_MODEL=<cross-encoder-model-id> \
uv run python app/scripts/retrieval_eval.py --repetitions 5
```

The run must execute modes A, B, C, and D against the same corpus snapshot and configuration. Only the retrieval mode may vary between rows.

### FR-04 — Metrics

For each mode, the output must report:

- Mean precision@5 over the 5 golden queries.
- Latency p50, p95, and mean in milliseconds.
- Delta precision@5 vs mode A.
- Delta latency vs mode A.
- Per-query retrieved budget ids and hit budget ids in `results.json`.

Precision is budget-level and deduplicated before scoring, matching the existing `precision_at_5` helper.

### FR-05 — Artifacts

The run must create a timestamped directory:

```text
evaluation/retrieval/results/<timestamp>/
├── results.json
├── comparison.md
└── recommendation.md
```

`comparison.md` is the main table for the exercise. `recommendation.md` must answer:

- Which mode should be used in the project and why?
- Does reranking justify its added latency for this concrete use case?

### FR-06 — Documentation

The implementation report must record:

- Evaluation date/time.
- Corpus snapshot notes, including number of chunks and budgets if available.
- Reranker model id.
- Retrieval settings used.
- Exact command executed.
- Test commands executed.
- What was not verified.
- Residual risk from the small golden set and local latency measurements.

## Technical Approach

Use the existing implementation as the system under test:

- `app/scripts/retrieval_eval.py` is the primary execution entrypoint.
- `app/embedding_pipeline/retrieval_eval.py` remains the source of truth for metric calculation and rendering.
- `app/embedding_pipeline/retrieval_service.py` remains the source of truth for A/B/C/D behavior.
- `evaluation/retrieval/golden_set.json` remains the committed golden set.

If small code hardening is necessary, keep it local to the evaluation path:

- Add preflight checks in `app/scripts/retrieval_eval.py` or a small helper under `app/embedding_pipeline/retrieval_eval.py`.
- Add deterministic tests under `tests/embedding_pipeline/test_retrieval_eval.py`.
- Do not require live DB, real OpenAI calls, or real reranker models in the default test suite.
- Mark any live evaluation test as `slow` and opt-in only.

The final recommendation should be committed as generated evidence, not hand-waved prose. If mode C/D cannot run because no suitable local reranker is available, this task is not complete; fix configuration or document the blocker instead of producing the final conclusion.

## Acceptance Criteria

- [ ] AC-01: A timestamped directory exists under `evaluation/retrieval/results/` containing `results.json`, `comparison.md`, and `recommendation.md`.
- [ ] AC-02: `results.json` includes all four modes A/B/C/D with per-query precision@5, latency samples, retrieved budget ids, and hit budget ids.
- [ ] AC-03: `comparison.md` includes one row per mode with mean precision@5, latency p50/p95/mean, delta precision vs A, and delta latency vs A.
- [ ] AC-04: `recommendation.md` explicitly chooses a production candidate mode and explains the precision/latency trade-off.
- [ ] AC-05: Modes C and D were run with a real non-noop reranker; the run does not silently degrade to A/B.
- [ ] AC-06: The final run uses `recall_k=50` and `top_k_final=5`; `rrf_k` and reranker model id are documented.
- [ ] AC-07: The golden-set labels are reviewed against the current corpus, and any changes are justified in `notes`.
- [ ] AC-08: The evaluation fails or is clearly blocked if the corpus is empty, embeddings are missing, `budget_id` metadata is absent, or the reranker is no-op.
- [ ] AC-09: No real secrets, local API keys, full prompts, embeddings, or sensitive `.env` values appear in committed artifacts.
- [ ] AC-10: Default offline tests pass with no real API keys and no live database.
- [ ] AC-11: Any new tests for preflight or artifact rendering are deterministic and do not call real external APIs.
- [ ] AC-12: Manual verification records Alembic/database readiness and a successful A/B/C/D evaluation run.
- [ ] AC-13: The work item's verification section is updated with exact commands, outputs, not-verified items, and residual risk.
- [ ] AC-14: `README.md` or `docs/technical/README.md` is updated only if the final execution workflow or interpretation guidance differs from current docs.

## Test Plan

- Unit tests:
  - Existing `tests/embedding_pipeline/test_retrieval_eval.py` remains green.
  - Add tests for any new preflight checks using fake settings/session results.
  - Add tests that no-op reranker detection blocks C/D evaluation.
- Integration tests:
  - Existing fake-based retrieval service tests remain green.
  - No new default test may require a real database, OpenAI API key, or cross-encoder download.
- Manual checks:
  - Run Alembic/database readiness checks against the evaluation database.
  - Run the full evaluation command with a configured non-noop reranker.
  - Inspect `comparison.md` and `recommendation.md` for consistency with `results.json`.

## Documentation Plan

- [x] Update this work item with the final verification log and generated artifact path.
- [x] Update `docs/technical/README.md` only if needed — not required; feature-050 docs sufficient.
- [x] Second Brain note updated: `learnings/.../retrieval-hybrid-vs-rerank-tradeoffs.md`.

## Implementation Plan

- [x] Step 1: Baseline review: confirm current git state, inspect `feature-050`, golden set, eval script, and absence/presence of result artifacts.
- [x] Step 2: Preflight validation: verify database readiness, Alembic head, chunk counts, embedding coverage, `budget_id` metadata, and non-noop reranker configuration.
- [x] Step 3: Golden-set review: check that the 5 labels exist in the corpus and update `notes` only if evidence requires it.
- [x] Step 4: Optional hardening: add small preflight or no-op safeguards if the runner can emit misleading artifacts; cover with deterministic tests.
- [x] Step 5: Run the full A/B/C/D evaluation with `recall_k=50`, `top_k_final=5`, fixed `rrf_k`, and a documented cross-encoder model.
- [x] Step 6: Review artifacts: validate `results.json`, `comparison.md`, and `recommendation.md` agree and contain no secrets or local-only sensitive data.
- [x] Step 7: Documentation and verification sweep: update this work item, relevant docs/Second Brain note if needed, run tests, and record residual risk.

## Learnings

- `feature-050` completed the retrieval capability and the evaluation harness, but a harness is not the same as evidence. This task must produce the actual run artifacts.
- Reranking modes are invalid if `RETRIEVAL_RERANK_MODEL` is empty or `RETRIEVAL_RERANK_ENABLED=false`; C/D must not be compared when they silently degrade to A/B.
- Precision labels are budget-level, while retrieval results are chunk-level. Deduplication before precision@5 is required to avoid overcounting repeated chunks from the same budget.
- Local latency is useful for relative comparison, but it is not a production SLA.
- With only 5 queries, the conclusion should be argued as directional evidence, not as a statistically robust benchmark.

## Estimation

- Size: M
- Estimated time: 2-4 hours, depending on database/model readiness.
- Planned steps: 7

## Implementation Progress

- [x] Step 1: Baseline review — feature-050 merged as base; golden set and eval harness confirmed.
- [x] Step 2: Preflight validation — Alembic 0004, 39 chunks, reranker `cross-encoder/ms-marco-MiniLM-L-6-v2`.
- [x] Step 3: Golden-set review — all 10 label budget ids present in corpus; notes updated.
- [x] Step 4: Preflight hardening — corpus/Alembic/rerank/golden coverage checks with unit tests.
- [x] Step 5: Full A/B/C/D run — `evaluation/retrieval/results/20260623T154959Z/`.
- [x] Step 6: Artifact review — no secrets; modes A–D consistent across JSON and markdown.
- [x] Step 7: Documentation and verification sweep — work item, Second Brain note, pytest green.

## Pull Request

- https://github.com/povedica/master-ia-lidr/pull/46 (draft, label `wip`)

## Verification

### Automated (2026-06-23)

- `uv run pytest tests/embedding_pipeline/test_retrieval_eval.py -q` → 12 passed
- `uv run pytest tests/embedding_pipeline/test_retrieval_service.py tests/embedding_pipeline/test_cross_encoder_reranker.py -q` → 9 passed
- `uv run pytest` → 620 passed, 11 skipped, 12 deselected

### Manual (2026-06-23)

- `DATABASE_URL=postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator uv run alembic current` → `0004`
- Corpus smoke: 39 chunks, 39 embeddings, 39 `content_tsv`, 39 `metadata.budget_id`, 25 distinct budgets
- Evaluation command:

```bash
DATABASE_URL=postgresql+asyncpg://estimator:estimator@127.0.0.1:5432/estimator \
RETRIEVAL_RERANK_ENABLED=true \
RETRIEVAL_RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2 \
RETRIEVAL_RECALL_K=50 \
RETRIEVAL_TOP_K_FINAL=5 \
RETRIEVAL_RRF_K=60 \
uv run python app/scripts/retrieval_eval.py --repetitions 5
```

- Artifacts: `evaluation/retrieval/results/20260623T154959Z/{results.json,comparison.md,recommendation.md}`
- Winner: **Mode B** (hybrid RRF, no rerank) — precision@5 0.240, p50 166.4 ms; reranking (C/D) reduced precision@5 to 0.120 with ~70 ms extra p50 latency on this corpus.

### Not verified

- Production latency or load under concurrent traffic
- Statistical significance (golden set has only 5 queries)
- Reranker quality with a larger or domain-tuned cross-encoder

### Residual risk

- Small golden set and mixed corpus (production budgets plus test/concurrency fixtures) make precision directional only.
- Local Docker Postgres latency differs from deployed environments.
- Rerank degraded precision here; a different model or larger recall pool might change the trade-off.

## Acceptance Criteria

- [x] AC-01: Timestamped directory `evaluation/retrieval/results/20260623T154959Z/` with all three artifacts.
- [x] AC-02: `results.json` includes modes A–D with per-query precision, latency samples, retrieved and hit budget ids.
- [x] AC-03: `comparison.md` includes delta precision and latency vs mode A for all modes.
- [x] AC-04: `recommendation.md` recommends mode B and states reranking did not justify latency in this run.
- [x] AC-05: Modes C/D ran with real `cross-encoder/ms-marco-MiniLM-L-6-v2` (non-noop).
- [x] AC-06: `recall_k=50`, `top_k_final=5`, `rrf_k=60`, reranker model documented above.
- [x] AC-07: Golden-set labels reviewed; corpus audit notes added per query.
- [x] AC-08: Preflight blocks empty corpus, stale Alembic, missing budget_id, and no-op reranker.
- [x] AC-09: Committed artifacts contain no secrets or `.env` values.
- [x] AC-10: Default offline pytest suite passes without live DB or API keys.
- [x] AC-11: New preflight tests are deterministic mocks/fakes only.
- [x] AC-12: Manual Alembic/corpus/evaluation run recorded above.
- [x] AC-13: Verification section updated in this work item.
- [x] AC-14: No README change required; existing feature-050 evaluation docs remain accurate.

## Repository commits (master-ia)

| Commit | Summary |
|--------|---------|
| (docs) | Add feature-051 work item |
| `feat(retrieval): add evaluation preflight checks for corpus and reranker` | Preflight validation + tests |
| `docs(retrieval): record golden-set corpus review for evaluation` | Golden-set audit notes |
| `feat(retrieval): add A/B/C/D evaluation evidence artifacts` | Committed run under `20260623T154959Z` |

## Handoff from feature-051

**Shipped:** Preflight gate in `app/embedding_pipeline/retrieval_eval.py` and `app/scripts/retrieval_eval.py`; golden-set corpus audit; committed evaluation artifacts recommending **mode B** (hybrid RRF without rerank) for the current local corpus.

**Evidence path:** `evaluation/retrieval/results/20260623T154959Z/`

**Settings used:** `RETRIEVAL_RECALL_K=50`, `RETRIEVAL_TOP_K_FINAL=5`, `RETRIEVAL_RRF_K=60`, `RETRIEVAL_RERANK_ENABLED=true`, `RETRIEVAL_RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2`, Alembic `0004`, Spanish FTS.

**Recommended next step for estimations:** Wire `RETRIEVAL_DEFAULT_MODE=B` (or explicit mode in retrieval calls) only after product review; reranking is not justified by this 5-query run.

**First checks for next implementer:** Re-run `uv run python app/scripts/retrieval_eval.py` after corpus ingest changes; confirm preflight passes; compare new `comparison.md` deltas before changing default mode.
