# Feature: Measurable Advanced Retrieval Capability (Hybrid + Rerank, Modes A/B/C/D)

> Product capability, not a one-off experiment. Promotes the internal retrieval primitives
> (epic `feature-041`…`feature-048`) into a first-class, configurable, **measurable** retrieval
> capability that the estimation product can rely on and that the team can tune with evidence.
> Promotes epic `feature-041`…`feature-048` into a production retrieval capability with modes A/B/C/D and an evaluation harness.

---

## Objective

### Problem

The current Retrieval-Augmented Generation (RAG) flow takes a project description, reformulates the
query, retrieves historical budgets by **vector similarity**, and feeds them as context to the
estimator. The failure mode is well known: *semantic similarity is not the same as estimation
relevance*. A pure-vector retriever can rank a "payments app" budget above an "e-commerce platform"
budget when the new request is actually closer to e-commerce, because the embedding captures topical
proximity rather than the structural/technical signals that make a past budget a good estimation
analogue. Exact technical tokens (frameworks, standards, acronyms, versions, integration names) are
exactly where embeddings are weakest and where lexical matching is strongest.

### What this feature delivers

A **production retrieval capability** that can operate in four explicit, reproducible modes and that
ships with a **built-in evaluation harness** to decide, with data, which mode to run in production:

- **A** — Vector search only, no reranking (current behavior, made explicit).
- **B** — Hybrid search (vector + lexical fused with Reciprocal Rank Fusion), no reranking.
- **C** — Vector search + cross-encoder reranking (recall-then-rerank).
- **D** — Hybrid search + cross-encoder reranking (recall-then-rerank).

Modes are selected by configuration / request parameter — **never by editing code** — and every run
is traceable to the exact configuration that produced it.

### Value to the product

- Higher retrieval **relevance** → better grounded estimations and fewer "irrelevant analogue"
  failures, without touching the generation prompt.
- A **repeatable measurement** of relevance (precision@5) vs **latency**, so retrieval quality stops
  being an opinion and becomes a number the team can defend.
- A clean extension point: when a new signal (e.g. a better reranker) appears, it plugs into the same
  contract and is evaluated with the same harness.

### Decision this enables

Stakeholders can answer, with evidence: *Which retrieval mode do we ship?* Specifically — does hybrid
beat vector on this corpus, does reranking add enough precision to justify its added latency, and what
is the production-candidate configuration. The real deliverable is **a measurable retrieval
capability**, not merely "add hybrid + reranker".

---

## 2. Product goals

### Functional goals

- One retrieval capability exposing modes A/B/C/D, selectable at request time and via a documented
  default setting.
- Lexical retrieval over the existing chunk corpus using PostgreSQL full-text search configured for
  **Spanish** (the corpus language), fused with the existing vector branch via RRF.
- Recall-then-rerank: broad recall (top-50), cross-encoder reordering, final selection (top-5).
- A reproducible evaluation that runs all four modes over a golden set and emits a comparison table.

### Quality goals

- Deterministic, side-effect-free fusion/ranking logic (already true for `fusion.py`; preserved).
- The default offline test suite stays green with no real API keys and no live database.
- Reranking and lexical search are individually toggleable; turning everything off reproduces today's
  vector-only behavior exactly (no silent behavior change).
- Structured logs carry mode + timing + counts, never query text, content, embeddings, or secrets.

### Business goals

- Replace subjective retrieval tuning with an auditable measurement.
- Produce an argued production recommendation that a non-engineer stakeholder can read.

### Expected improvement over current retrieval

- Measurable lift in **precision@5** for queries dominated by exact technical tokens (where vector
  alone under-ranks the right budget), with hybrid and/or rerank modes.
- A documented latency cost per mode so the precision/latency trade-off is explicit rather than
  assumed.

---

## 3. Stakeholders

| Profile | Uses / benefits from | Needs from this feature |
| --- | --- | --- |
| **Business / Sales ops** | More relevant analogue budgets → more credible estimates | A plain-language recommendation: which mode and why, with the precision/latency table |
| **Product** | Decides default retrieval mode and acceptable latency budget | Clear comparison of the four modes; the ability to flip the default without a release that touches code |
| **Engineering (backend)** | Owns the retrieval service and endpoint | Stable contracts, feature flags, safe fallbacks, offline tests, no router-level model construction |
| **AI / ML** | Owns relevance quality and the reranker | A reproducible eval harness, a golden set, and a rerank extension point behind a stable protocol |
| **Operations / SRE** | Runs it in production | Latency visibility per mode, kill switches, and the guarantee that disabling features restores baseline |

---

## Context

This feature **reuses and promotes** the internal retrieval-debug epic; it does not reimplement it:

- `app/embedding_pipeline/fusion.py` — RRF reused as-is.
- `app/embedding_pipeline/rerank.py` — `Reranker` protocol reused; `CrossEncoderReranker` added.
- `app/embedding_pipeline/lexical_search_repository.py` — reused; text-search config made Spanish.
- `app/embedding_pipeline/search_repository.py` — vector recall reused unchanged.
- `POST /api/v1/retrieval-debug` stays the **diagnostic** surface (diff, explanations); this feature
  adds a lean **production** surface (`POST /api/v1/retrieval`) plus the measurement loop.

**Assumptions:** chunk corpus ingested with embeddings and metadata; Postgres with pgvector (0002) and
lexical indexes (0003); migration `0004` switches FTS to Spanish; evaluation needs a populated DB;
default unit suite stays offline.

---

## Scope

### Includes

- **Spanish full-text search**: migration to (re)generate `chunks.content_tsv` with the `spanish`
  text-search configuration, keep the GIN index, and switch the lexical repository query/headline to
  `spanish`.
- **Lexical + hybrid as a production capability**: reuse `LexicalSearchRepository` and
  `app/embedding_pipeline/fusion.py` (`reciprocal_rank_fusion`) to produce a single coherent fused
  ranking outside the debug-only path.
- **Cross-encoder reranking**: a real `Reranker` implementation behind the existing protocol
  (`app/embedding_pipeline/rerank.py`), wired as recall(top-50) → rerank → top-5, toggleable.
- **Four modes A/B/C/D**: a `RetrievalMode` selector exposed via request parameter and a default
  setting; deterministic mapping from mode → branches + rerank.
- **Production retrieval entrypoint**: a `RetrievalService` and an HTTP endpoint that returns the
  final ranked results plus the applied mode and timings.
- **Evaluation framework**: a golden set (5 queries with manual relevance labels), a runner that
  executes A/B/C/D, computes precision@5 and latency, and writes a comparison table + machine-readable
  results + an argued recommendation.

### Excludes

- Query expansion.
- Query decomposition.
- Multi-index routing.
- Metadata filtering (the filter primitives exist in the debug path; the production modes here do **not**
  add or require them).
- Any change to augmentation or generation (prompt assembly, the estimator output).
- Broad RAG pipeline redesign beyond the retrieval stage.
- Wiring the chosen mode into the live estimation generation call — that is a **follow-up** once the
  recommendation exists (kept out because it is an augmentation/generation change).

### Assumptions and dependencies

- The chunk corpus is already ingested with embeddings and metadata (`budget_id`, `component_id`,
  `year`, `main_technology`, `client_sector`, `source_name`, …) per the embedding pipeline.
- PostgreSQL with `pgvector`, the HNSW index (migration `0002`), and the lexical column/indexes
  (migration `0003`) are present. This feature adds migration `0004`.
- The corpus content is predominantly **Spanish**; the existing `content_tsv` uses `english`, which is
  the concrete gap this feature corrects.
- A cross-encoder model wrapper is integrated behind the `Reranker` protocol; the concrete model id and
  runtime (local sentence-transformers vs hosted) is a design decision (see §12), but the **contract**
  (`Reranker`, `RerankCandidate`, `RerankedItem`) already exists and must not change.
- Evaluation runs require a populated database; the default unit suite must not.

---

## Functional Requirements

### FR-01 — Invocation

Two entry points, same underlying `RetrievalService`:

1. **HTTP** — `POST /api/v1/retrieval` (new, production-facing).
2. **CLI / evaluation** — `app/scripts/retrieval_eval.py` (runs modes over the golden set).

The capability is also reachable internally as `RetrievalService.retrieve(...)` so the estimation
service can later consume it (follow-up, out of scope here).

### FR-02 — Modes supported

`mode` is one of `A`, `B`, `C`, `D` (case-insensitive). The mode deterministically resolves to a
branch set and a rerank flag:

| Mode | Vector | Lexical + RRF fusion | Cross-encoder rerank |
| --- | --- | --- | --- |
| A | yes | no | no |
| B | yes | yes | no |
| C | yes | no | yes |
| D | yes | yes | yes |

A `mode` parameter is mandatory in the request, **or** it falls back to the documented default setting
`RETRIEVAL_DEFAULT_MODE`. The mode actually applied is always echoed back in the response.

### FR-03 — Inputs

```jsonc
// POST /api/v1/retrieval
{
  "query": "string (required, non-empty, already-reformulated text)",
  "mode": "A | B | C | D (optional; defaults to RETRIEVAL_DEFAULT_MODE)",
  "top_k_final": 5,            // optional, 1..50, default 5
  "recall_k": 50               // optional, 1..200, default 50 (recall width before rerank/fusion cap)
}
```

- `query` is the (already reformulated) retrieval text; this feature does **not** reformulate.
- `recall_k` is the breadth of the initial recall stage (per branch). For rerank modes it is the
  candidate pool the cross-encoder reorders.
- `top_k_final` is the final cut after fusion/rerank.

### FR-04 — Outputs

```jsonc
{
  "query": "…",
  "mode": "D",
  "applied_config": {
    "mode": "D",
    "branches": ["vector", "lexical"],
    "fusion": { "method": "rrf", "rrf_k": 60 },
    "rerank": { "enabled": true, "model": "<reranker-id>", "is_noop": false },
    "recall_k": 50,
    "top_k_final": 5,
    "text_search_config": "spanish"
  },
  "timings_ms": { "vector": 0, "lexical": 0, "fusion": 0, "rerank": 0, "total": 0 },
  "results": [
    {
      "final_position": 1,
      "chunk_id": 123,
      "document_id": 45,
      "budget_id": "BUD-2023-014",
      "score": 0.83,                 // final score for the active mode (fusion or rerank score)
      "vector_score": 0.71,          // nullable per mode
      "lexical_score": 0.64,         // nullable per mode
      "fusion_score": 0.0123,        // nullable per mode
      "rerank_score": 0.92,          // nullable per mode
      "matched_terms": ["oauth2", "stripe"],
      "source_strategies": ["vector", "lexical", "rerank"],
      "metadata": { "...": "..." }
    }
  ],
  "warnings": []
}
```

- Per-mode nullability: e.g. mode A has no `lexical_score`/`fusion_score`/`rerank_score`; mode B has no
  `rerank_score`; modes C/D populate `rerank_score`.
- The result row reuses the existing `BranchResultEntry`/`DebugResult` field conventions where
  practical, but the production response is a **separate, smaller schema** (no `diff`, no explanation
  vocabulary) to keep the product contract lean. Diagnostics stay on `/api/v1/retrieval-debug`.

### FR-05 — Configuration admitted

- `RETRIEVAL_DEFAULT_MODE` (`A|B|C|D`, default `A` to preserve current behavior).
- `RETRIEVAL_LEXICAL_TEXT_SEARCH_CONFIG` (default `spanish`).
- `RETRIEVAL_RERANK_ENABLED` (global kill switch; when `false`, modes C/D degrade to A/B with a
  warning, never a hard failure).
- `RETRIEVAL_RERANK_MODEL` (reranker id; empty ⇒ `NoOpReranker`, which makes C/D behave like A/B and
  emits a no-op warning, exactly as the existing placeholder does).
- `RETRIEVAL_RECALL_K` (default 50) and `RETRIEVAL_TOP_K_FINAL` (default 5) defaults.
- `RETRIEVAL_RRF_K` (default 60).

### FR-06 — Behavior per mode (summary; full flow in §7)

- **A**: embed query → vector top-`recall_k` → cut to `top_k_final`.
- **B**: vector top-`recall_k` + lexical top-`recall_k` → RRF fuse → cut to `top_k_final`.
- **C**: vector top-`recall_k` → cross-encoder rerank → cut to `top_k_final`.
- **D**: vector + lexical → RRF fuse top-`recall_k` → cross-encoder rerank → cut to `top_k_final`.

A branch failure degrades gracefully (partial result + `warnings`), mirroring the existing debug
orchestrator's `asyncio.gather(..., return_exceptions=True)` contract.

### FR-07 — Evaluation artifacts produced

Running the evaluation produces, under a versioned results directory:

- `comparison.md` — the human-facing table (one row per mode: precision@5, latency p50/p95/mean,
  Δ vs baseline mode A).
- `results.json` — machine-readable per-query and per-mode metrics (precision@5, latency samples,
  retrieved ids, hit ids).
- `recommendation.md` — an argued production recommendation referencing the numbers.

---

## Technical Approach

### Database changes

- **Migration `0004_set_chunks_content_tsv_spanish.py`** (`down_revision = "0003"`):
  - Recreate `chunks.content_tsv` as
    `GENERATED ALWAYS AS (to_tsvector('spanish', content)) STORED` (drop + re-add the generated column,
    or `ALTER` per the chosen Postgres-compatible path; document the approach).
  - Recreate the GIN index `ix_chunks_content_tsv_gin` over the regenerated column.
  - Keep the `pg_trgm` trigram index from `0003` unchanged.
  - `downgrade()` restores the `english` generated column + GIN index (round-trip safe).
- `app/models/chunk.py` keeps mapping `content_tsv: Mapped[str | None]` (`TSVECTOR`); no model field
  change, only the underlying generation config changes.

> Rationale: migration `0003` shipped `content_tsv` with `to_tsvector('english', …)`. For a Spanish
> corpus this stems and stop-words incorrectly. This is the concrete full-text gap to close.

### Retrieval services / modules

- **New** `app/embedding_pipeline/retrieval_service.py`:
  - `RetrievalMode` enum (`A`, `B`, `C`, `D`) + `resolve_mode(mode) -> RetrievalPlan` mapping a mode to
    `{branches, fusion_enabled, rerank_enabled}`.
  - `RetrievalService.retrieve(query, *, mode, recall_k, top_k_final, session, embedder, reranker)` →
    `RetrievalResponse`.
  - Orchestrates: recall (vector and/or lexical, concurrently) → optional RRF fusion → optional rerank
    → final cut. This **reuses** `SemanticSearchRepository`, `LexicalSearchRepository`,
    `reciprocal_rank_fusion`, and the `Reranker` protocol; it must not duplicate fusion math.
- **New** `app/routers/retrieval.py`: `POST /api/v1/retrieval`, DI for session/embedder/reranker
  exactly like `app/routers/search.py` and `app/routers/retrieval_debug.py` (router constructs no model
  directly; reranker is injected).
- **New** schemas in `app/embedding_pipeline/retrieval_schemas.py`: `RetrievalRequest`,
  `RetrievalResponse`, `RetrievalResultRow` (lean production contract).

### Lexical retriever integration

- Switch `LexicalSearchRepository` `websearch_to_tsquery`/`ts_headline` from `"english"` to a
  configurable text-search config (default `spanish`, from settings). Keep the
  `content_tsv @@ websearch_to_tsquery(...)` + `ts_rank_cd(content_tsv, ...)` shape and the
  `matched_terms` derivation (`ts_headline` markup) unchanged in structure.
- The lexical branch output is normalized to `[0,1]` exactly as `build_lexical_branch_entries` does
  today (min-max over branch-local `ts_rank_cd`, all-equal ⇒ `1.0`).

### RRF integration

- Reuse `reciprocal_rank_fusion(branch_rankings, k=rrf_k)` from `fusion.py`. For modes B and D, fuse
  `{"vector": vector_entries, "lexical": lexical_entries}` to a single ranking, then cut.
- Weighted fusion is **available but not exposed** as a mode here (RRF is the default and only fusion
  in scope); leave weights out of the production request to keep the four-mode contract crisp.

### Reranker integration

- Add a concrete `CrossEncoderReranker` implementing the existing `Reranker` protocol
  (`async def rerank(query, candidates) -> list[RerankedItem]`, `is_noop = False`).
- It scores each `RerankCandidate` (`query`, candidate `content`) with the cross-encoder, sorts
  descending, assigns `rerank_rank` (1-based) and a normalized `rerank_score ∈ [0,1]`.
- Recall-then-rerank: the candidate pool is the recall stage output (vector top-`recall_k`, or fused
  top-`recall_k` for mode D); after rerank, take `top_k_final` (5).
- Resolution: `RETRIEVAL_RERANK_MODEL` empty ⇒ `NoOpReranker` (modes C/D become A/B + warning).
  Non-empty ⇒ `CrossEncoderReranker`. The reranker is injected via DI; the router never builds the
  model.
- `RerankCandidate.content` must carry the **full chunk content**, not a truncated excerpt — this fixes
  the residual risk noted in `feature-045` where the debug path passed an excerpt.

### Suggested contracts / interfaces

```python
class RetrievalMode(str, Enum):
    A = "A"  # vector only
    B = "B"  # hybrid (vector + lexical RRF)
    C = "C"  # vector + rerank
    D = "D"  # hybrid + rerank

@dataclass(frozen=True)
class RetrievalPlan:
    branches: tuple[str, ...]      # ("vector",) or ("vector", "lexical")
    fusion_enabled: bool
    rerank_enabled: bool

def resolve_mode(mode: RetrievalMode) -> RetrievalPlan: ...

class RetrievalService:
    async def retrieve(
        self,
        query: str,
        *,
        mode: RetrievalMode,
        recall_k: int,
        top_k_final: int,
        session: AsyncSession,
        embedder: OpenAIEmbedder,
        reranker: Reranker,
    ) -> RetrievalResponse: ...
```

```python
# Evaluation
@dataclass(frozen=True)
class GoldenQuery:
    id: str
    query: str
    relevant_budget_ids: frozenset[str]   # manual labels (relevance = good estimation analogue)

@dataclass(frozen=True)
class ModeMetrics:
    mode: RetrievalMode
    precision_at_5: float        # mean over golden queries
    latency_ms_p50: float
    latency_ms_p95: float
    latency_ms_mean: float
    per_query: list[QueryResult]
```

### Configuration and feature flags

New `Settings` fields (typed, documented in `.env.example`):

```text
RETRIEVAL_DEFAULT_MODE=A
RETRIEVAL_LEXICAL_TEXT_SEARCH_CONFIG=spanish
RETRIEVAL_RECALL_K=50
RETRIEVAL_TOP_K_FINAL=5
RETRIEVAL_RRF_K=60
RETRIEVAL_RERANK_ENABLED=false
RETRIEVAL_RERANK_MODEL=
```

- Backward-compatible defaults: with everything default, only mode A is reachable as default and it
  equals today's vector path. Lexical/rerank are opt-in.

### Logging and observability (minimum)

- One structured `retrieval_completed` log per request with: `request_id`, `mode`, branch counts
  (`vector_count`, `lexical_count`, `fused_count`, `final_count`), `timings_ms`, `rerank_is_noop`.
- **Never** log query text, chunk content, embeddings, matched terms, or secrets.
- Latency for each stage (`vector`, `lexical`, `fusion`, `rerank`, `total`) is measured with
  `time.perf_counter()` exactly like the existing orchestrator.

### Performance and scalability

- Vector recall uses the HNSW index (`0002`); lexical uses the GIN index on `content_tsv` (`0003`/`0004`).
- The cross-encoder is the dominant latency cost; bound it by reranking at most `recall_k` candidates
  and document expected latency per mode in the evaluation output.
- Vector and lexical branches run concurrently (`asyncio.gather`); fusion is pure and cheap.
- Reranker calls should be batched (single forward pass over `recall_k` pairs) where the wrapper allows.

### Future extensibility points

- Additional retrieval branches (e.g. trigram/`pg_trgm` exact-token branch) can be added to the
  `RetrievalPlan.branches` set and fused without changing the response contract.
- Alternative fusion (weighted, learned) plugs into the existing `fusion.py` seam.
- Alternative rerankers (LLM-as-reranker, hosted cross-encoder) are drop-in `Reranker` implementations.
- The evaluation harness is metric-agnostic enough to add recall@k or nDCG later without redesign.

---

## 7. Retrieval modes (A/B/C/D)

For all modes: `query` is embedded once if a vector branch is used; `recall_k` defaults to 50,
`top_k_final` defaults to 5.

### Mode A — Vector only, no rerank

- **Purpose:** baseline; the current production behavior, made explicit and measurable.
- **Flow:** embed → `SemanticSearchRepository.search_chunks(k=recall_k)` → take top `top_k_final`.
- **Top-k:** recall `recall_k` (50), final `top_k_final` (5).
- **Output:** rows with `vector_score`; `lexical_score`/`fusion_score`/`rerank_score` null.
- **When it makes sense:** lowest latency; queries already well served by embeddings; the control group.

### Mode B — Hybrid (vector + lexical RRF), no rerank

- **Purpose:** add the orthogonal lexical signal to recover exact-token matches embeddings miss.
- **Flow:** vector top-`recall_k` ∥ lexical top-`recall_k` → `reciprocal_rank_fusion(k=rrf_k)` →
  take top `top_k_final`.
- **Top-k:** recall `recall_k` per branch, fused list cut to `top_k_final`.
- **Output:** rows with `vector_score`, `lexical_score`, `fusion_score`, `matched_terms`; no
  `rerank_score`.
- **When it makes sense:** corpora/queries rich in acronyms, frameworks, standards, identifiers;
  modest latency increase over A.

### Mode C — Vector + rerank

- **Purpose:** isolate the value of reranking on top of pure vector recall.
- **Flow:** vector top-`recall_k` → `CrossEncoderReranker.rerank(query, candidates)` →
  take top `top_k_final`.
- **Top-k:** recall `recall_k` (50), rerank reorders the pool, final `top_k_final` (5).
- **Output:** rows with `vector_score` and `rerank_score`; `rerank_score` drives final order.
- **When it makes sense:** when embeddings retrieve the right pool but order it poorly; isolates rerank
  effect from hybrid effect.

### Mode D — Hybrid + rerank

- **Purpose:** the full pipeline; best expected relevance, highest latency.
- **Flow:** vector ∥ lexical → RRF fuse top-`recall_k` → `CrossEncoderReranker` → take top
  `top_k_final`.
- **Top-k:** recall `recall_k` per branch, fused to `recall_k`, rerank, final `top_k_final` (5).
- **Output:** rows with `vector_score`, `lexical_score`, `fusion_score`, `rerank_score`,
  `matched_terms`.
- **When it makes sense:** when both recall breadth (hybrid) and ordering (rerank) matter and the
  latency budget allows it; the likely production candidate to validate.

---

## 8. Evaluation framework

### 8.1 Defining the golden set

- A versioned file `evaluation/retrieval/golden_set.json` (committed, no secrets) with **5**
  representative domain queries.
- Each entry: `{ "id", "query", "relevant_budget_ids": [...], "notes" }`.
- Queries chosen to cover the failure space deliberately: at least 2 dominated by exact technical
  tokens (where lexical should help), at least 1 paraphrase/semantic case (where vector should help),
  and 1–2 mixed.
- Relevance labels are added **manually** by a domain reviewer; the rationale per query is recorded in
  `notes` so the labeling is auditable and reproducible.

### 8.2 What "relevant" means in this domain

A retrieved chunk/budget is **relevant** when its source budget is a *good estimation analogue* for the
query — i.e. a human estimator would reasonably reuse its scope/components/effort as a reference. It is
**not** enough to be topically similar. Labels are at the **budget** level (`budget_id`); a retrieved
chunk counts as a hit if its `budget_id` is in the query's `relevant_budget_ids`.

### 8.3 Computing precision@5

- For each query and mode, take the final top-5 results, map each to its `budget_id`, and dedupe to
  unique budgets (a budget appearing in multiple chunks counts once).
- `precision@5 = (# of top-5 unique budgets that are labeled relevant) / 5`.
- Report the **mean precision@5** across the 5 golden queries per mode, plus per-query values.
- Document the deduplication rule explicitly, since chunk-level vs budget-level counting changes the
  number.

### 8.4 Measuring latency

- Wall-clock per request via `time.perf_counter()`, captured per stage and total (already supported).
- Run **N repetitions** per (query, mode) after a warm-up pass; report p50, p95, and mean of `total`.
- Exclude the first (cold) run from percentiles; document `N` (default 5) and warm-up.

### 8.5 Guaranteeing comparable runs

- Same corpus snapshot, same embedding model, same DB, same machine, single run session.
- Disable any semantic/inference cache for the eval (cache would distort latency and relevance).
- Pin `recall_k`, `top_k_final`, `rrf_k`, and the reranker model across modes; only the **mode**
  varies. Record the full resolved config in `results.json`.
- The runner executes all four modes back-to-back for each query to share warm caches/connections.

### 8.6 Biases and limitations to watch

- **Tiny golden set (5):** precision@5 is coarse and noisy; treat differences as directional, not
  statistically significant. State this in the recommendation.
- **Labeler bias:** single-reviewer labels can be subjective; record rationale and allow re-labeling.
- **Corpus drift:** results are valid for the current corpus snapshot; re-run after major ingests.
- **Latency variance:** local measurements ≠ production; report relative deltas, not absolute SLAs.
- **Rerank no-op trap:** if `RETRIEVAL_RERANK_MODEL` is empty, C/D silently equal A/B — the harness must
  detect `is_noop` and fail loudly / annotate the table, so a "no improvement" conclusion is never
  drawn from an accidental no-op.

---

## 9. Deliverables

- **Code**
  - `app/embedding_pipeline/retrieval_service.py` (`RetrievalMode`, `resolve_mode`, `RetrievalService`).
  - `app/embedding_pipeline/retrieval_schemas.py` (`RetrievalRequest`, `RetrievalResponse`,
    `RetrievalResultRow`).
  - `app/routers/retrieval.py` (`POST /api/v1/retrieval`) + registration in `app/main.py`.
  - `CrossEncoderReranker` in `app/embedding_pipeline/rerank.py` (behind the existing protocol).
  - Spanish text-search config wired into `LexicalSearchRepository` (configurable, default `spanish`).
  - Evaluation runner `app/scripts/retrieval_eval.py` + metric helpers
    `app/embedding_pipeline/retrieval_eval.py` (precision@5, latency aggregation, table rendering).
- **Migrations**
  - `alembic/versions/0004_set_chunks_content_tsv_spanish.py` (regenerate `content_tsv` as `spanish` +
    GIN index; round-trip downgrade to `english`).
- **Configuration**
  - New `Settings` fields (§6.7) and `.env.example` entries with safe defaults.
- **Scripts / endpoints**
  - `POST /api/v1/retrieval` (production) and `app/scripts/retrieval_eval.py` (evaluation CLI).
- **Golden set**
  - `evaluation/retrieval/golden_set.json` (5 queries + manual `relevant_budget_ids` + notes).
- **Evaluation results**
  - `evaluation/retrieval/results/<timestamp>/results.json`.
- **Comparison table**
  - `evaluation/retrieval/results/<timestamp>/comparison.md` (A/B/C/D × precision@5, latency
    p50/p95/mean, Δ vs A).
- **Final recommendation**
  - `evaluation/retrieval/results/<timestamp>/recommendation.md` — argued production candidate.
- **Docs**
  - `README.md`, `docs/technical/README.md`, and `docs/arquitectura-estimador-cag.html` updated; a
    Second Brain note on hybrid vs rerank trade-offs.

---

## Acceptance Criteria

- [x] AC-01: Migration `0004` regenerates `chunks.content_tsv` with `to_tsvector('spanish', content)`
      and a GIN index; `alembic downgrade 0003` restores the `english` definition (round-trip verified).
- [x] AC-02: `LexicalSearchRepository` uses a configurable text-search config defaulting to `spanish`
      for `websearch_to_tsquery` and `ts_headline`; lexical response shape is unchanged.
- [x] AC-03: `RetrievalMode` + `resolve_mode` map A/B/C/D to the exact branch/fusion/rerank plan in §5.2
      (unit-tested, deterministic).
- [x] AC-04: `POST /api/v1/retrieval` accepts `mode` (or applies `RETRIEVAL_DEFAULT_MODE`) and echoes
      the applied mode + resolved config in the response.
- [x] AC-05: Mode A returns vector-only top-5 identical in ordering to the current
      `SemanticSearchRepository` path (no behavior regression).
- [x] AC-06: Mode B fuses vector + lexical via `reciprocal_rank_fusion` into one ranking cut to
      `top_k_final`, with `fusion_score` and `matched_terms` populated.
- [x] AC-07: Modes C and D run recall(top-`recall_k`) → cross-encoder rerank → top-`top_k_final`, with
      `rerank_score` driving final order.
- [x] AC-08: `CrossEncoderReranker` implements the existing `Reranker` protocol unchanged
      (`is_noop = False`) and receives **full chunk content** in `RerankCandidate.content`.
- [x] AC-09: With `RETRIEVAL_RERANK_MODEL` empty (or `RETRIEVAL_RERANK_ENABLED=false`), modes C/D degrade
      to A/B and emit a clear no-op/disabled `warnings` entry — never a 500.
- [x] AC-10: A branch failure produces a partial result + `warnings`, not a hard error (gather contract
      preserved).
- [x] AC-11: Golden set file exists with 5 queries and manual `relevant_budget_ids`; schema validated.
- [x] AC-12: `retrieval_eval.py` runs all four modes over the golden set and computes mean precision@5
      (budget-level, deduped) and latency p50/p95/mean per mode.
- [x] AC-13: The runner emits `comparison.md`, `results.json`, and `recommendation.md`; the table shows
      Δ precision@5 and Δ latency vs mode A.
- [x] AC-14: The eval detects a no-op reranker (`is_noop`) and annotates/fails so C/D are never silently
      equal to A/B.
- [x] AC-15: Structured logs include mode, counts, timings; no query text, content, embeddings, or
      secrets are logged.
- [x] AC-16: `POST /api/v1/search` and `POST /api/v1/retrieval-debug` are unchanged (regression-safe).
- [x] AC-17: Default offline test suite passes with no real API key and no live DB; eval tests that need
      a model/DB are marked `slow`/opt-in per testing standards.
- [x] AC-18: `.env.example`, `README.md`, technical docs, and architecture HTML document the modes,
      flags, Spanish FTS, and the evaluation workflow.

---

## Test Plan

- **Unit tests**
  - `resolve_mode` for A/B/C/D (branch set, fusion flag, rerank flag).
  - Precision@5 helper: budget-level dedup, partial hits, empty results, all-relevant, none-relevant.
  - Latency aggregation: p50/p95/mean, cold-run exclusion, single-sample edge case.
  - `CrossEncoderReranker` ordering with a fake scorer (no real model): higher score ⇒ lower rank;
    `is_noop = False`.
  - Comparison-table rendering from synthetic `ModeMetrics`.
- **Integration tests** (offline, fakes)
  - `RetrievalService.retrieve` for each mode using a fake embedder + fake repositories + fake/no-op
    reranker; assert branch composition, fusion, rerank application, and final cut.
  - No-op/disabled rerank degradation path (C→A, D→B) emits the warning.
  - Branch-failure partial-result path.
  - `POST /api/v1/retrieval` request/response contract + empty-`DATABASE_URL` → safe `503`.
- **Static / migration tests**
  - `tests/test_alembic_migration.py`: `0004` regenerates `content_tsv` as `spanish` + GIN index;
    downgrade restores `english`.
- **Manual checks** (Compose Postgres, opt-in)
  - `alembic upgrade head`; `\d chunks`; lexical query with Spanish tokens vs English baseline.
  - curl `/api/v1/retrieval` for each mode; confirm field nullability and timings.
  - Run `retrieval_eval.py`; inspect `comparison.md` and `recommendation.md`.

---

## Verification

- **Automated:** `uv run pytest` — `616 passed, 11 skipped, 12 deselected` (2026-06-21).
- **Automated (targeted):** `tests/embedding_pipeline/test_retrieval_service.py`,
  `test_retrieval_router.py`, `test_retrieval_eval.py`, `test_cross_encoder_reranker.py`,
  `tests/test_alembic_migration.py`, `tests/test_config.py`.
- **Manual (opt-in / live DB):** Compose Postgres migration round-trip; curl `/api/v1/retrieval` per mode;
  full `retrieval_eval.py` run with rerank model configured.
- **Not verified:** real cross-encoder quality/latency on populated corpus; statistical significance of
  precision@5 with 5 golden queries; production SLAs.

## Handoff from feature-050

Shipped interfaces:

- `POST /api/v1/retrieval` with modes A/B/C/D, lean `RetrievalResponse`, stage timings, and warnings.
- `RetrievalService.retrieve(...)` for internal reuse; estimation wiring remains a follow-up.
- Settings: `RETRIEVAL_*` in `app/config.py` and `.env.example`.
- Migration `0004_set_chunks_content_tsv_spanish.py` (Spanish FTS).
- `CrossEncoderReranker` + `build_reranker(settings)` behind existing `Reranker` protocol.
- Evaluation: `evaluation/retrieval/golden_set.json`, `app/embedding_pipeline/retrieval_eval.py`,
  `app/scripts/retrieval_eval.py`.

Recommended first checks for follow-up (wire mode into estimation):

- `tests/embedding_pipeline/test_retrieval_service.py` — mode matrix with fakes.
- `tests/embedding_pipeline/test_retrieval_router.py` — HTTP contract + 503 without DB.

Residual risks: golden-set labels need domain review; rerank adds `sentence-transformers` + torch weight;
eval CLI requires live DB and API key.

## Repository commits (master-ia)

| Commit | Summary |
| --- | --- |
| docs | Normalize feature-050 work item headers for start-task gate |
| feat | Spanish FTS migration 0004 + configurable LexicalSearchRepository |
| feat | RETRIEVAL_* settings and defaults |
| feat | RetrievalService modes A-D, production endpoint, CrossEncoderReranker |
| feat | Evaluation harness, golden set, retrieval_eval CLI |
| docs | README, technical docs, architecture HTML, Second Brain, work-item closure |
| `8a2871d` | `feat(web): link retrieval debug screen from home` |

---

## 13. Documentation plan

- [x] `README.md`: new `/api/v1/retrieval` capability, the four modes, flags, and how to run the
  evaluation.
- [x] `docs/technical/README.md`: mode → plan mapping, recall-then-rerank, Spanish FTS migration rationale,
  RRF reuse, reranker contract, evaluation methodology (precision@5 dedup rule, latency protocol,
  biases).
- [x] `docs/arquitectura-estimador-cag.html`: add the production retrieval node and the evaluation loop.
- [x] Second Brain: a learning note on hybrid vs rerank trade-offs and how to read the comparison table.
- [x] `.env.example`: all new `RETRIEVAL_*` variables with safe defaults.

---

## Estimation

- Size: L
- Estimated time: 6–8 hours
- Planned steps: 7

## Implementation progress

- [x] Step 1: **Spanish FTS** — migration `0004` + static migration tests; make
      `LexicalSearchRepository` text-search config configurable (default `spanish`); repository tests.
      *Validate:* migration round-trip + lexical statement shape before proceeding.
- [x] Step 2: **Settings `RETRIEVAL_*`** — typed config + `.env.example`; config tests.
- [x] Step 3: **Mode resolver + service (A/B)** — `RetrievalMode`, `resolve_mode`, `RetrievalService`;
      unit + integration tests with fakes. *Validate:* A equals vector path; B fuses correctly.
- [x] Step 4: **Production endpoint** — `retrieval_schemas.py`, `app/routers/retrieval.py`, register in
      `main.py`; contract tests + safe `503` on empty `DATABASE_URL`. *Validate:* A/B over HTTP.
- [x] Step 5: **Cross-encoder reranker + modes C/D** — `CrossEncoderReranker`, DI + flags, no-op
      degradation + warnings; tests with fake scorer. *Validate:* C/D reorder; degradation safe.
- [x] Step 6: **Evaluation framework** — golden set, metric helpers, `retrieval_eval.py` runner,
      artifact rendering, no-op detection; unit tests.
- [x] Step 7: **Docs + final verification** — README, technical docs, architecture HTML, Second Brain,
      `.env.example`; full suite; handoff section.

**PR:** https://github.com/povedica/master-ia-lidr/pull/45 (draft WIP)

### Technical risks that would block progress

- **No-op reranker masquerading as a real one** → eval conclusions invalid (mitigated by AC-14 / Step 4
  warning + Step 5 detection).
- **Spanish migration on a generated column**: if `ALTER`-in-place is not supported, fall back to
  drop+re-add inside the migration; verify on Compose before relying on it.
- **Reranker latency/availability**: a slow or unavailable model must degrade gracefully, never block
  retrieval (kill switch + no-op fallback).
- **Empty / unpopulated corpus during eval** → precision@5 undefined; the runner must fail with a clear
  message rather than emit misleading zeros.

---

## Open questions / design decisions

1. **Reranker model & runtime:** which concrete cross-encoder (e.g. a multilingual
   `cross-encoder/ms-marco-*` vs a Spanish-tuned model) and where it runs (in-process
   sentence-transformers vs hosted endpoint). Impacts latency, dependencies, and `.env`.
2. **Spanish vs multilingual FTS config:** `spanish` regconfig vs `simple` + trigram, given mixed
   Spanish/English technical tokens in the corpus. Decide and document.
3. **Generated-column migration strategy:** in-place `ALTER` of the generation expression vs
   drop+re-add; confirm on the target Postgres version.
4. **Budget-level vs chunk-level precision:** confirmed budget-level + dedup in §8.3 — ratify with the
   domain reviewer.
5. **Recall width (`recall_k`) default:** 50 per the prompt; revisit if rerank latency is too high or
   recall too shallow.
6. **Final response schema source of truth:** a dedicated lean schema (proposed) vs reusing
   `DebugResult`. Proposed: dedicated, to keep the production contract minimal.
7. **Where the chosen mode is consumed in production:** wiring into the estimation generation call is a
   follow-up (augmentation/generation is out of scope here) — confirm the handoff owner.
8. **Eval determinism for the reranker:** if the model is non-deterministic, pin seeds / eval mode and
   document residual variance.
