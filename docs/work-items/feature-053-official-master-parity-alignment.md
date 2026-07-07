# Feature: Official Master Parity Alignment (`ai-engineering` → `master-ia`)

## Objective

Bring `master-ia` to **functional and technical parity** with the official Master IA repository (`/Users/pablo.poveda/CodeProjects/ai-engineering`, package `estimator`) for every capability that both projects share conceptually, while **preserving deliberate fork choices** (Langfuse observability, React `web/` UI, work-item docs, provider chain, `/api/v2/estimate`, streaming, retrieval-debug tooling).

This work item is the **canonical roadmap** for closing the gap. It does **not** implement everything in one pass; it defines scope, priorities, file-level mapping, acceptance gates, and baby-step sequencing so follow-up features (`feature-054+`) or `/start-task` slices can be executed safely.

### Comparison snapshot (2026-07-06)

| Repo | Branch | Role |
| --- | --- | --- |
| `master-ia` | `feature/052-rag-line-citations-ragas-eval` | Student fork (this repo) |
| `ai-engineering` | `session_11_live` | Official master monorepo |

**Layout difference (non-goal to replicate verbatim):** official code lives under `estimator/app/{foundation,domain,generation,ingestion,api}`; `master-ia` uses `app/{services,embedding_pipeline,guardrails,routers}`. Parity means **behavior and contracts**, not a folder rename.

---

## Context

### What `master-ia` already matches or exceeds

| Area | `master-ia` status | Official reference |
| --- | --- | --- |
| CAG estimation v1/v2 | `/api/v1/estimate`, `/api/v2/estimate`, SSE stream | Only `/api/v1/estimate` |
| Provider abstraction | `llm_chain.py`, `provider_routing.py`, multi-provider fallback | `LLMWrapper` + primary/fallback |
| Semantic cache | Redis + in-memory, wired in `LLMPipeline` | `EstimationSemanticCache` |
| Guardrails pipeline | `LLMPipeline`, 7 declarative policies, rollout modes | Input/output guardrails (narrower) |
| ACB orchestration | `ActorCriticBossOrchestrator` on session estimate | `Boss` + `Critic` on `/sessions/.../estimate-acb` |
| Observability | Langfuse + Logfire adapters | `structlog` only |
| Session API | `/api/v1/sessions/*`, multipart attachments | `/sessions/*` (no `/api/v1` prefix) |
| Embedding ingest (budgets) | `POST /api/v1/embeddings/ingest`, transactional persist | `POST /embeddings/ingest` |
| Retrieval modes A–D | `RetrievalService`, hybrid RRF, optional rerank | S09 pipeline + S10 advanced |
| Retrieval debug | `POST /api/v1/retrieval-debug`, React screen | Not present |
| RAG estimation (baseline) | `POST /api/v1/estimate/rag`, `verify_citations()` | `POST /v1/estimate/from-transcript` full S11 loop |
| RAGAS offline eval | `generation_eval.py`, `ragas_generation_eval.py` | `eval_generation_s11.py` with gate/monitor |
| Retrieval offline eval | `retrieval_eval.py`, golden set, recommendation | `eval_retrieval_s10.py`, `StageConfig` matrix |
| Postgres + pgvector | `documents` / `chunks`, Alembic 0001–0004 | `budget_chunks` + multi-index 0004–0005 |
| Work items / Second Brain | `docs/work-items/`, `learnings/` | None |

### Prior architectural decisions (do not reopen without ADR)

`docs/work-items/adr-001-embedding-pipeline-vs-estimator-ingestion.md` explicitly **deferred** from the official ingestion stack:

- YAML data catalog with audit scores
- Presidio / Pandera cleaning in the hot path
- Postgres `ingestion_jobs` + 202/poll for batch catalog ingest

**This parity feature respects ADR-001** for the budget embedding path but still ports **selective S06 patterns** where they improve RAG quality (PII on transcripts, cleaning validators) behind explicit new work items.

### In-flight work (`feature-052`) — prerequisite, not duplicate

`feature-052` ships the **first** RAG line-citation path. Remaining gaps from that work item feed directly into Phase 1 of this roadmap:

| `feature-052` follow-up | Parity phase |
| --- | --- |
| RAGAS `answer_relevancy` NaN + JSON-safe metrics | Phase 1 — Eval harness |
| Web citations table UI | Phase 1 — UI parity (React, not Rails) |
| Low `context_recall` tuning | Phase 2 — Retrieval quality |

Do **not** re-implement `verify_citations`, `RagEstimationService`, or `POST /api/v1/estimate/rag` under this feature; extend them.

---

## Scope

### Includes

1. **Gap inventory and phased plan** (this document).
2. **RAG S09–S11 parity**: query reformulation, augmentation, hallucination gate, coherence check, multi-index retrieval, advanced pipeline stages, task-hours flow, corpus expansion.
3. **API hardening parity**: API keys, rate limiting, idempotency, request-ID correlation (adapted to `master-ia` logging conventions).
4. **Runtime configuration parity**: Redis-backed model and retrieval toggles without server restart.
5. **Conversation memory parity**: anchor detection + cumulative summarization (beyond sliding window).
6. **Eval harness parity**: regression gate (`--gate`), named stage configs, monitor mode, baseline comparison with exit codes.
7. **Chunking lab parity**: strategy comparison endpoint/CLI (at least structural + 2–3 strategies useful for teaching).
8. **Selective ingestion parity**: transcript + technical-doc parsers and multi-index persistence (without replacing ADR-001 budget path).
9. **Documentation**: parity matrix in `docs/technical/README.md`, session note cross-links.

### Excludes

- **Rails `estimator-web`** wizard — `master-ia` keeps React `web/`; parity is **capability**, not framework.
- **Monorepo restructure** (`foundation/` / `generation/` rename).
- **Replacing Langfuse/Logfire** with `structlog`.
- **Removing** `/api/v2/estimate`, streaming, semantic cache, or `LLMPipeline` guardrails.
- **Full Presidio + catalog pipeline** in one shot (ADR-001); optional phased sub-feature only.
- **IVFFlat / halfvec / SQL antipattern scripts** from S08 unless a measured need appears.
- **Committing** generated eval artifacts under `evaluation/**/results/` (keep local or CI artifacts).

---

## Parity matrix (detailed)

Legend: ✅ done · 🟡 partial · ❌ missing · 🔵 fork-only (keep)

### A. HTTP API surface

| Capability | Official (`estimator`) | `master-ia` | Target |
| --- | --- | --- | --- |
| Health | `GET /health` | `GET /health`, `GET /` | ✅ |
| CAG estimate | `POST /api/v1/estimate` | `POST /api/v1/estimate` | ✅ |
| CAG structured v2 | — | `POST /api/v2/estimate` | 🔵 keep |
| SSE streaming | — | `POST /api/v1/estimate/stream` | 🔵 keep |
| Sessions CRUD | `POST/GET /sessions/{id}` | `POST/GET /api/v1/sessions/{id}` | ✅ (prefix differs) |
| Session estimate multipart | `POST /sessions/{id}/estimate` | `POST /api/v1/sessions/{id}/estimate` | ✅ |
| Session ACB | `POST /sessions/{id}/estimate-acb` | via `acb_enabled` on session estimate | 🟡 expose dedicated route optional |
| Budget ingest | `POST /embeddings/ingest` | `POST /api/v1/embeddings/ingest` | ✅ |
| Chunking compare | `POST /embeddings/compare` | — | ❌ Phase 3 |
| Semantic search (legacy) | `POST /search` (no auth) | `POST /api/v1/search` | ✅ |
| Retrieval (measurable) | `POST /v1/retrieval/search` | `POST /api/v1/retrieval` (modes A–D) | 🟡 extend with S10 |
| Advanced retrieval | `POST /v1/retrieval/advanced-search` | — | ❌ Phase 2 |
| RAG end-to-end | `POST /v1/estimate/from-transcript` | `POST /api/v1/estimate/rag` (question-only) | 🟡 Phase 1–2 |
| RAG stage wizard | `POST /v1/estimate/stages/{reformulate,retrieve,assemble,structure,generate,verify}` | — | ❌ Phase 2 |
| Task hours | `POST /v1/estimate/tasks/hours` | — | ❌ Phase 2 |
| Corpus index jobs | `POST /embeddings/index/runs`, poll, stats | — | ❌ Phase 3 |
| Batch ingestion jobs | `POST /api/v1/ingestion/runs` | — | ❌ Phase 4 (optional) |
| Runtime model config | `GET/PUT /api/v1/config/models` | `GET/PUT /api/v1/config/models` (Redis override) | ✅ feature-057 |
| Runtime retrieval config | `GET/PUT /api/v1/config/retrieval` | `GET/PUT /api/v1/config/retrieval` (Redis override, wired to rerank) | ✅ feature-057 |
| Retrieval debug | — | `POST /api/v1/retrieval-debug` | 🔵 keep |
| API key auth | `RETRIEVAL_API_KEY`, `ESTIMATE_API_KEY` | none | ❌ Phase 1 |
| Rate limiting | `slowapi` per key | none | ❌ Phase 1 |
| Idempotency | 24h on `from-transcript` | none | ❌ Phase 2 |
| Request ID | `X-Request-ID` middleware | partial via logging `request_id` in RAG | 🟡 Phase 1 |

### B. RAG generation pipeline (S09–S11)

| Stage | Official module | `master-ia` module | Gap |
| --- | --- | --- | --- |
| Query reformulation | `generation/rag/query_reformulator.py` | — | ❌ `EstimationQuery` from transcript/question |
| Search text composition | `compose_search_text()` | uses raw `question` string | ❌ |
| Retrieval (basic) | `retrieval/pipeline.py` | `embedding_pipeline/retrieval_service.py` | 🟡 single `chunks` table vs multi-index |
| Retrieval (advanced) | `retrieval/advanced_pipeline.py` | — | ❌ routing, query transform, temporal decay |
| Multi-index collections | `retrieval/collections.py` | single `chunks` + `metadata_filters` | ❌ budgets / transcripts / technical_docs |
| Reranking | `retrieval/reranker.py` | `embedding_pipeline/rerank.py` (`NoOpReranker` default) | 🟡 enable + wire in prod path |
| Context assembly | `context_assembler.py` | `services/rag_context_assembler.py` | 🟡 no token budget truncation |
| Token budget truncate | `truncate_to_token_budget()` | — | ❌ |
| Augmentation S11 | `quality/augmentation.py` | — | ❌ compress + edge-loading reorder |
| Generation | `estimator.py:generate_estimate()` | `RagEstimationService` + `complete_structured()` | 🟡 no structure-only mode |
| Structure-only pass | `generate_structure()` | — | ❌ |
| Referential citations | `validation.py:verify_citations()` | `citation_verification.py` | 🟡 align status enum names |
| Coherence check | `validation.py:check_coherence()` | `rag_coherence.py` | ✅ feature-058 |
| Hallucination gate | `quality/hallucination.py` | — | ❌ anchor + judge + `gate_estimate()` |
| Synthesis S11 | `quality/synthesis.py` | — | ❌ contradiction ranges |
| Task-level hours | `task_hours.py` | — | ❌ per-task vector retrieval |
| Idempotency store | `idempotency.py` + Redis | — | ❌ |
| End-to-end orchestrator | `estimate_from_transcript()` | `RagEstimationService.estimate()` | 🟡 missing S10/S11 stages |

### C. Data model and persistence

| Entity | Official | `master-ia` | Gap |
| --- | --- | --- | --- |
| Budget chunks | `budget_chunks` table | `chunks` + `documents` | 🟡 different schema, same role |
| Transcript chunks | `transcript_chunks` | — | ❌ migration + ingest |
| Technical doc chunks | `technical_doc_chunks` | — | ❌ |
| HNSW index | migration `0005` | `0002_add_chunks_embedding_hnsw_index` | 🟡 verify params vs official |
| FTS / tsvector | migration `0003` | `0003`, `0004` Spanish config | ✅ comparable |
| Jobs / index runs | `jobs` repository | — | ❌ Phase 3 |
| PII mappings | `MappingsRepository` | — | ❌ Phase 4 optional |

### D. Ingestion and chunking

| Capability | Official | `master-ia` | Gap |
| --- | --- | --- | --- |
| Budget JSON parser | `ingestion/parsers/budget_json.py` | `embedding_pipeline/parsers/budget_json.py` | ✅ |
| Transcript parser | `transcript_txt.py` | — | ❌ |
| Catalog-driven batch | `ingestion/orchestrator.py` | ADR-001 deferred | ❌ optional Phase 4 |
| PII Presidio | `ingestion/pii/*` | — | ❌ optional Phase 4 |
| Structural chunker | `chunking/structural.py` | `embedding_pipeline/chunker.py` | ✅ |
| 7 chunking strategies | `chunking/strategies/*` | structural only | ❌ Phase 3 (subset) |
| Chunking compare API | `POST /embeddings/compare` | CLI `compare.py` only | 🟡 |
| Corpus build scripts | `build_multi_index_corpus.py`, etc. | `ingest_from_dir.py`, fixtures | 🟡 |

### E. Conversation / CAG (S05)

| Capability | Official | `master-ia` | Gap |
| --- | --- | --- | --- |
| Session store | `SessionStore` | `InMemorySessionStore` | ✅ same trade-off |
| Metadata extraction | `metadata_extractor.py` | `metadata_extractor.py` | ✅ |
| Sliding window | `ConversationHistory` | `ConversationHistory` max_turns | ✅ |
| Anchor detection | `compression/anchors.py` | — | ❌ Phase 3 |
| Cumulative summarizer | `compression/summarizer.py` | — | ❌ Phase 3 |
| Compression policy | `compression/policy.py` | — | ❌ Phase 3 |
| Tier resolver | `tier_resolver.py` | — | ❌ low priority |
| Boss/Critic | `agentic/boss.py`, `critic.py` | `guardrails/acb/` | ✅ equivalent |

### F. Security and operations

| Capability | Official | `master-ia` | Gap |
| --- | --- | --- | --- |
| API keys (retrieval/estimate) | `api/security.py` | — | ❌ Phase 1 |
| Rate limits | `api/rate_limiting.py` + slowapi | — | ❌ Phase 1 |
| Runtime config Redis | `foundation/llm/runtime_config.py` | `app/services/runtime_config.py` | ✅ feature-057 |
| Request ID middleware | `main.py` | per-handler `request_id` | 🟡 unify |
| Dev/prod config split | `APP_ENV` patterns | `app_env`, `dev_mode` | ✅ |

### G. Evaluation and quality gates

| Capability | Official | `master-ia` | Gap |
| --- | --- | --- | --- |
| Retrieval golden set | `evals/golden_retrieval.json` | `evaluation/retrieval/golden_set.json` | ✅ |
| Generation golden set | `evals/golden_generation_s11.json` | `evaluation/generation/golden_set.json` | ✅ |
| Retrieval eval script | `eval_retrieval_s10.py` + `StageConfig` | `retrieval_eval.py` modes A–D | 🟡 map StageConfig ↔ modes |
| RAGAS baseline doc | `evals/RAGAS_BASELINE_S11.md` | local run only | 🟡 commit baseline template |
| Generation gate | `eval_generation_s11.py --gate` exit ≠ 0 | no gate / no exit code | ❌ Phase 1 |
| Monitor mode | `--monitor` faithfulness + relevancy | — | ❌ Phase 1 |
| Named configs | `--config full` toggles S11 features | — | ❌ Phase 2 |
| Compare configs | `--compare` scoreboard | — | ❌ Phase 2 |
| Isolated RAGAS scorer | `score_ragas_s11.py` | single venv `ragas==0.4.3` | 🟡 document venv split |
| Citation demo script | `demo_verify_citations_s11.py` | tests only | 🟡 optional CLI |
| Stress test | `evals/stress/run.py` | `evals/stress/run.py` | ✅ |
| Session golden YAML | `evals/run.py` actor/acb | `tests/evals/` | ✅ richer in master-ia |

### H. Frontend / UX

| Capability | Official (`estimator-web`) | `master-ia` (`web/`) | Gap |
| --- | --- | --- | --- |
| Estimation form | Rails wizard | React estimation feature | ✅ |
| RAG wizard steps | 6-step ERB partials | — | ❌ Phase 2 (React) |
| Citations table | S11 UI | planned in feature-052 Step 16 | 🟡 |
| Retrieval debug | — | gated `VITE_ENABLE_RETRIEVAL_DEBUG` | 🔵 keep |
| Chunking lab UI | Rails | — | ❌ Phase 3 optional |

---

## Functional Requirements

### Phase 0 — Close `feature-052` tail (prerequisite)

- **FR-00a:** Fix RAGAS `answer_relevancy` by passing a natural-language answer string to RAGAS (not raw `model_dump_json()`).
- **FR-00b:** Serialize `metrics.json` with JSON-safe floats (`null` for non-finite); use `nanmean` for aggregates.
- **FR-00c:** Ship React citations table for `POST /api/v1/estimate/rag` responses (`component`, `hours`, `grounded`, `rationale`, `sources[]`, audit counts).

### Phase 1 — API hardening + eval gate + RAGAS baseline (S11 foundation)

- **FR-01:** Add optional API key auth for retrieval and RAG estimate endpoints (`RETRIEVAL_API_KEY`, `ESTIMATE_API_KEY`); when unset, dev mode allows open access (documented).
- **FR-02:** Integrate `slowapi` rate limits aligned with official defaults (retrieval 120/min, estimate 10/min per key).
- **FR-03:** Add global `X-Request-ID` middleware; propagate ID to stdlib logging `extra={"request_id": ...}` (no `structlog`).
- **FR-04:** Implement `RuntimeModelConfig` and `RuntimeRetrievalConfig` with Redis overrides; expose `GET/PUT /api/v1/config/models` and `GET/PUT /api/v1/config/retrieval`.
- **FR-05:** Extend `ragas_generation_eval.py` with `--gate`, `--monitor`, baseline comparison, non-zero exit on regression; document baseline in `evaluation/generation/RAGAS_BASELINE.md`.
- **FR-06:** Add `check_coherence()` after generation (ported logic from official `validation.py`, adapted to `RagEstimationResult`).

### Phase 2 — RAG S10/S11 core pipeline

- **FR-07:** Implement `query_reformulator` producing `EstimationQuery` from free-text question/transcript; wire into `RagEstimationService` before retrieval.
- **FR-08:** Add `truncate_to_token_budget()` to context assembly using `tiktoken` (reuse settings pattern from official).
- **FR-09:** Implement hallucination gate: `numeric_anchor()`, `judge_estimate()` (batched LLM via `complete_structured`), `gate_line()`, `gate_estimate()`; extend `RagEstimationResponse` with `HallucinationReport` / per-line grades (`grounded` / `degraded` / `insufficient`).
- **FR-10:** Implement `augment_chunks()` (compress + edge-loading reorder); toggle via `Settings` + runtime config.
- **FR-11:** Implement `advanced_retrieve()` with `StageConfig` dataclass: query transform, routing, hard filters, hybrid per collection, RRF vs round-robin fusion, temporal decay; expose `POST /api/v1/retrieval/advanced`.
- **FR-12:** Add stage endpoints under `POST /api/v1/estimate/rag/stages/*` (reformulate, retrieve, assemble, generate, verify) — stateless, reusing same pure functions as orchestrator.
- **FR-13:** Support transcript-shaped input on RAG path (`POST /api/v1/estimate/rag` accepts `transcript` optional field; reformulator runs when present).
- **FR-14:** Implement `estimate/tasks/hours` endpoint: structure-only generation + per-task retrieval for hours (port `task_hours.py` semantics).
- **FR-15:** Add idempotency for RAG estimate (`Idempotency-Key` header, Redis TTL 24h).

### Phase 3 — Multi-index, corpus growth, chunking lab

- **FR-16:** Alembic migration: `transcript_chunks` and `technical_doc_chunks` (or unified `chunks` with `collection` discriminator — prefer **discriminator column** on existing `chunks` to limit migration churn; document choice in implementation).
- **FR-17:** Transcript + technical-doc parsers and ingest path (CLI + optional API).
- **FR-18:** `CorpusIndexService` with async job pattern (202 + poll) or synchronous MVP behind `dev_mode` first.
- **FR-19:** `POST /api/v1/embeddings/compare` — compare ≥3 chunking strategies on sample document; return metrics (chunk count, avg size, embedding cost estimate).
- **FR-20:** Port `eval_retrieval_s10.py` **StageConfig** matrix; map existing modes A–D to named configs for backward compatibility.

### Phase 4 — Conversation compression + selective ingestion (optional)

- **FR-21:** Hybrid memory compression: `AnchorDetector`, `CumulativeSummarizer`, `CompressionPolicy` integrated into `ConversationHistory` / session estimate path.
- **FR-22:** Synthesis module for contradiction detection across chunk ranges (`quality/synthesis.py` parity).
- **FR-23:** Presidio PII on transcript ingest only (behind feature flag); pseudonym map table — **only if** a new ADR approves scope change.

### Cross-cutting

- **FR-24:** All new settings documented in `.env.example` and `README.md`.
- **FR-25:** Layering invariant preserved: `app/services` → `app/embedding_pipeline`; no reverse imports.
- **FR-26:** Default pytest remains fast; LLM-judge and RAGAS gate tests marked `@pytest.mark.slow`.
- **FR-27:** Official parity does not break existing `/api/v2/estimate`, semantic cache, or `LLMPipeline` contracts.

---

## Technical Approach

### File mapping (official → `master-ia` target)

| Official (`estimator/app/...`) | Proposed `master-ia` location |
| --- | --- |
| `generation/rag/query_reformulator.py` | `app/services/rag_query_reformulator.py` |
| `generation/rag/context_assembler.py` (truncate) | extend `app/services/rag_context_assembler.py` |
| `generation/rag/validation.py` | extend `app/services/citation_verification.py` + `rag_coherence.py` |
| `generation/rag/quality/hallucination.py` | `app/services/rag_hallucination_gate.py` |
| `generation/rag/quality/augmentation.py` | `app/embedding_pipeline/rag_augmentation.py` |
| `generation/rag/quality/synthesis.py` | `app/embedding_pipeline/rag_synthesis.py` |
| `generation/rag/retrieval/advanced_pipeline.py` | `app/embedding_pipeline/advanced_retrieval.py` |
| `generation/rag/retrieval/collections.py` | `app/embedding_pipeline/collections.py` |
| `generation/rag/retrieval/query_transform.py` | `app/embedding_pipeline/query_transform.py` |
| `generation/rag/retrieval/router.py` | `app/embedding_pipeline/retrieval_router.py` |
| `generation/rag/retrieval/temporal.py` | `app/embedding_pipeline/temporal_decay.py` |
| `generation/rag/task_hours.py` | `app/services/rag_task_hours.py` |
| `generation/rag/idempotency.py` | `app/services/rag_idempotency.py` |
| `foundation/llm/runtime_config.py` | `app/services/runtime_config.py` |
| `api/security.py`, `api/rate_limiting.py` | `app/middleware/security.py`, `app/middleware/rate_limiting.py` |
| `api/routers/estimate_stages.py` | `app/routers/rag_stages.py` |
| `api/routers/retrieval_advanced.py` | extend `app/routers/retrieval.py` or `retrieval_advanced.py` |
| `api/routers/estimate_tasks.py` | `app/routers/rag_task_hours.py` |
| `api/routers/corpus_index.py` | `app/routers/corpus_index.py` |
| `api/config.py` | `app/routers/runtime_config.py` |
| `generation/conversation/compression/*` | `app/services/conversation_compression/` |
| `scripts/eval_generation_s11.py` | extend `app/scripts/ragas_generation_eval.py` |

### Orchestrator target shape (`RagEstimationService`)

After parity, `estimate()` should follow official order (each stage skippable via `StageConfig` / settings):

```text
reformulate_query → compose_search_text → retrieve (basic or advanced)
  → augment_chunks → build_context_block → truncate_to_token_budget
  → generate_estimate → verify_citations → check_coherence → gate_estimate
```

Keep **`complete_structured` + Instructor** (not raw OpenAI Responses API). Keep **stdlib logging** with `extra={}`.

### `StageConfig` vs retrieval modes A–D

| `master-ia` mode | Official `StageConfig` analogue |
| --- | --- |
| A (vector only) | `search_mode=vector`, `rerank=false`, routing off |
| B (hybrid RRF) | `search_mode=hybrid`, `rerank=false` |
| C (vector + rerank) | `search_mode=vector`, `rerank=true` |
| D (hybrid + rerank) | `search_mode=hybrid`, `rerank=true` |

Advanced S10 adds dimensions **not** expressible as A–D: multi-index routing, query decomposition, temporal decay. Eval harness should report both schemes during transition.

### Dependencies to add (when implementing phases)

| Package | Phase | Notes |
| --- | --- | --- |
| `slowapi` | 1 | Rate limiting |
| `redis` | already present | Runtime config + idempotency |
| `presidio-analyzer`, `presidio-anonymizer`, `spacy` | 4 optional | Heavy; dev/group optional |
| `langchain-text-splitters` | 3 optional | Chunking strategies |

Do **not** add `structlog`.

### Settings additions (preview)

```text
# Phase 1
RETRIEVAL_API_KEY=
ESTIMATE_API_KEY=
RATE_LIMIT_ENABLED=true

# Phase 2 — RAG S11
HALLUCINATION_GATE_ENABLED=false
HALLUCINATION_JUDGE_MODEL=
REFORMULATION_MODEL=
AUGMENTATION_ENABLED=false
SYNTHESIS_ENABLED=false
RAG_IDEMPOTENCY_TTL_SECONDS=86400

# Phase 2 — S10 retrieval
RETRIEVAL_ROUTING_ENABLED=false
QUERY_TRANSFORM_ENABLED=false
RETRIEVAL_TEMPORAL_DECAY_ENABLED=false
```

---

## Acceptance Criteria

### Phase 0 (feature-052 completion)

- [ ] **AC-01:** `uv run python app/scripts/ragas_generation_eval.py` produces finite `answer_relevancy` for all golden queries.
- [ ] **AC-02:** `metrics.json` validates as strict JSON (no bare `NaN`).
- [ ] **AC-03:** React UI renders per-line citations and citation audit summary for RAG responses.

### Phase 1

- [ ] **AC-04:** With `ESTIMATE_API_KEY` set, `POST /api/v1/estimate/rag` without key returns 401; with key succeeds.
- [ ] **AC-05:** Exceeding rate limit returns 429 (tested with mocked limiter or low threshold in test).
- [ ] **AC-06:** Every response includes `X-Request-ID`; logs include same id in `extra`.
- [ ] **AC-07:** `PUT /api/v1/config/retrieval` changes rerank toggle without restart; subsequent retrieval honors it.
- [ ] **AC-08:** `ragas_generation_eval.py --gate` exits non-zero when faithfulness mean drops below baseline − tolerance (deterministic mock mode for CI).
- [ ] **AC-09:** `check_coherence()` integrated; incoherent sample fails deterministically in unit test. _(✅ feature-058)_

### Phase 2

- [ ] **AC-10:** RAG path with reformulator improves retrieval P@5 on paraphrase query `q3-crm-paraphrase` vs raw question (document in eval note).
- [ ] **AC-11:** Hallucination gate marks inflated-hours line as `degraded` in unit test with canned chunks.
- [ ] **AC-12:** `POST /api/v1/retrieval/advanced` returns chunks with `collection` provenance labels.
- [ ] **AC-13:** Stage endpoint `POST /api/v1/estimate/rag/stages/verify` returns citation + hallucination reports without running full pipeline.
- [ ] **AC-14:** `POST /api/v1/estimate/rag/tasks/hours` returns per-task hours with citations.
- [ ] **AC-15:** Duplicate `Idempotency-Key` within TTL returns cached response body.

### Phase 3

- [ ] **AC-16:** Ingest transcript fixture → searchable via advanced retrieval in `transcripts` collection.
- [ ] **AC-17:** `POST /api/v1/embeddings/compare` returns strategy comparison for bundled sample.
- [ ] **AC-18:** `eval_retrieval` supports named `StageConfig` and prints scoreboard comparable to official `eval_retrieval_s10.py`.

### Phase 4 (if approved)

- [ ] **AC-19:** Long session (≥15 turns) retains anchor facts after compression (integration test).
- [ ] **AC-20:** Synthesis detects contradictory hour ranges in fixture and flags range.

### Global

- [ ] **AC-21:** `uv run pytest` passes (fast suite) after each merged slice.
- [ ] **AC-22:** No secrets in committed files; `.env.example` updated per phase.
- [ ] **AC-23:** `docs/technical/README.md` parity matrix section updated.
- [ ] **AC-24:** `/api/v2/estimate` and session CAG paths regression-tested unchanged.

---

## Test Plan

### Unit tests

- Port patterns from official tests where behavior is ported:
  - `tests/generation/rag/test_hallucination.py` → `tests/test_rag_hallucination_gate.py`
  - `tests/test_advanced_pipeline.py` → `tests/embedding_pipeline/test_advanced_retrieval.py`
  - `tests/api/test_security.py`, `test_rate_limiting.py`, `test_idempotency.py`
  - `tests/test_query_transform.py`, `test_router_rules.py`
- Mock all LLM and embedding calls; use `FakeLLMProvider` / existing fakes.

### Integration tests

- RAG full pipeline with TestClient + mocked provider returning canned `RagEstimationResult`.
- Advanced retrieval against SQLite/Postgres test container (existing embedding_pipeline patterns).
- Runtime config round-trip with `fakeredis` if added.

### Manual checks

1. Run official and fork eval harness on same golden set; compare metric tables.
2. Exercise React RAG stages UI (when built) against stage endpoints.
3. `docker compose up` smoke: ingest budget → retrieval advanced → RAG estimate with citations + gate.

### Heavy / slow

- Live RAGAS gate with real API keys: `@pytest.mark.slow`, `uv run pytest --run-heavy`.
- Cross-encoder reranker model download: document one-time setup in README.

---

## Verification

| Check | Command / action |
| --- | --- |
| Fast tests | `uv run pytest` |
| Targeted RAG tests | `uv run pytest tests/test_rag_* tests/embedding_pipeline/test_advanced_*` |
| RAGAS gate (local) | `uv run python app/scripts/ragas_generation_eval.py --gate` |
| Retrieval eval | `uv run python app/scripts/retrieval_eval.py` |
| Lint (if ruff added) | optional; not blocking unless repo adopts ruff |
| Manual API | Swagger `/docs` + `api-collection/` |

**Not verified at spec time:** live parity numbers vs official baseline on same hardware (requires both repos running with keys).

**Residual risk:** semantic differences from schema shapes (`RagEstimationResult` vs official `Estimate`) may prevent byte-identical eval scores; acceptance is **relative improvement + gate stability**, not numeric equality with official repo.

---

## Documentation Plan

| Artifact | Update |
| --- | --- |
| `README.md` | Parity status table, new endpoints, env vars |
| `.env.example` | All new variables per phase |
| `docs/technical/README.md` | Parity matrix (abbreviated), architecture diagram |
| `evaluation/generation/RAGAS_BASELINE.md` | Baseline means + tolerance (template from official `RAGAS_BASELINE_S11.md`) |
| `learnings/docs/sesiones/` | Session note when each phase completes |
| `docs/work-items/feature-054+` | Split concrete slices from this roadmap |

---

## Implementation Plan

This roadmap should be executed as **multiple child work items**, not one `/start-task` mega-diff.

### Recommended child work items

| ID | Slug | Phase | Depends on |
| --- | --- | --- | --- |
| feature-054 | `agentic-estimation-loop` | Session 12 | — _(out of parity track; see `feature-054-agentic-estimation-loop.md`)_ |
| feature-055 | `ragas-eval-gate-and-monitor` | 0 | feature-052 |
| feature-055b | `web-rag-citations-table` | 0 | feature-052 _(shipped in feature-052)_ |
| feature-056 | `api-security-rate-limit-request-id` | 1 | — |
| feature-057 | `runtime-config-redis-endpoints` | 1 | feature-056 |
| feature-058 | `rag-coherence-and-eval-gate` | 1 | feature-055, feature-057 |
| feature-059 | `rag-query-reformulator-and-token-budget` | 2 | feature-058 |
| feature-060 | `rag-hallucination-gate` | 2 | feature-059 |
| feature-061 | `advanced-retrieval-s10-pipeline` | 2 | feature-059 |
| feature-062 | `rag-stage-endpoints-and-task-hours` | 2 | feature-060, feature-061 |
| feature-063 | `multi-index-corpus-and-chunking-compare` | 3 | feature-061 |
| feature-064 | `conversation-compression-s05` | 4 | — |
| feature-065 | `transcript-pii-ingest-optional` | 4 | ADR-002 if needed |

### Baby steps (first slice to `/start-task`)

- [x] **Step 1:** Complete feature-052 Steps 15–17 (RAGAS fix + UI).
- [x] **Step 2:** `feature-056` — API keys + slowapi + `X-Request-ID` middleware. _(PR — https://github.com/povedica/master-ia-lidr/pull/48)_
- [x] **Step 3:** `feature-055` — `--gate` / `--monitor` on generation eval. _(PR — https://github.com/povedica/master-ia-lidr/pull/49)_
- [x] **Step 3b:** `feature-057` — runtime config Redis endpoints. _(merged PR #50, 2026-07-07)_
- [x] **Step 4:** `feature-058` — `check_coherence()` + eval gate integration on RAG path. _(PR — https://github.com/povedica/master-ia-lidr/pull/51)_
- [ ] **Step 5:** `feature-059` — query reformulator + token budget wired into `RagEstimationService`.
- [ ] **Step 6:** `feature-060` — hallucination gate behind `HALLUCINATION_GATE_ENABLED`.
- [ ] **Step 7:** `feature-061` — `advanced_retrieve` + endpoint.
- [ ] **Step 8:** `feature-062` — stage routes + task hours.
- [ ] **Step 9:** `feature-063` — multi-index migration + ingest.
- [ ] **Step 10:** Update parity matrix in `docs/technical/README.md` to ✅ per row.

---

## Learnings

1. **Do not port folder structure blindly.** Official `generation/rag/` maps cleanly onto `master-ia`'s `services/` + `embedding_pipeline/` split if dependency direction is enforced.
2. **`verify_citations` ≠ quality gate.** Official S11 teaches referential integrity first, semantic hallucination gate second — `master-ia` has only the first.
3. **Eval gate is a product feature.** Official `--gate` exit codes enable CI blocking; fork's eval scripts are informative only until Phase 1.
4. **ADR-001 still valid** for budget ingest; multi-index parity may use a `collection` column rather than three tables to reduce migration pain — decide in `feature-063` implementation note.
5. **React vs Rails:** stage wizard UX should call the same stage endpoints official uses; no need for Rails.
6. **Keep fork advantages:** Langfuse traces, retrieval-debug, v2 structured API, and work-item discipline are not gaps to close.
7. **RAGAS dependency isolation:** official uses separate venv for scoring; document the same if `langchain-community` conflicts resurface.
8. **Baseline run `20260629T185540Z`** proves retrieval precision is strong (0.863) but recall (0.140) and answer relevancy (broken) need work before claiming S11 parity.
9. **Parallel wave 1 (2026-07-06):** `worktree_tasks.py` + manifest `docs/technical/feature-053-parity-parallel.manifest.yaml` prepared two worktrees; child slices shipped as separate WIP PRs (#49, #50). Review merge order: #48 → #49/#50 → next wave.
10. **Wave 2 prep (2026-07-07):** `feature-058` dependency corrected (055+057, not 054). Work items 058–061 authored; wave 2 manifest at `docs/technical/feature-053-parity-parallel-wave2.manifest.yaml`. `feature-054` stays Session 12 track, optional parallel with 058.

---

## Estimation

| Phase | Relative effort | Risk |
| --- | --- | --- |
| 0 (052 tail) | S | Low |
| 1 | M | Low–medium |
| 2 | L | Medium (many LLM calls) |
| 3 | L | Medium (migrations) |
| 4 | M | High (Presidio weight) |

**Total:** multi-session; treat as program track, not single PR.

---

## Implementation progress (program track)

- [x] Phase 0 — feature-052 complete (merged PR #47)
- [x] Phase 1 Step 2 — feature-056 API hardening (merged PR #48, 2026-07-07)
- [x] Phase 1 Step 3 — feature-055 RAGAS gate/monitor (merged PR #49, 2026-07-07)
- [x] **Parallel wave 1 — feature-057** runtime config (merged PR #50, 2026-07-07)
- [x] **Parallel wave 2 — feature-058** RAG coherence (merged PR #51, 2026-07-07)

### Session 12 track (outside parity wave)

`feature-054-agentic-estimation-loop.md` is a **separate Session 12 exercise** (agentic loop + CLI deliverable). It is **not** on the parity critical path and does **not** block `feature-058`. The draft work item exists locally (untracked until committed); it may run **in parallel** with `feature-058` in a second worktree when desired (`mutex_group: agentic` vs `rag-pipeline`).

### Parallel orchestration (wave 1)

| Task | Work item | Branch | Parallel with |
| --- | --- | --- | --- |
| 055 | `feature-055-ragas-eval-gate-and-monitor.md` | `feature/055-ragas-eval-gate-and-monitor` | 057 |
| 057 | `feature-057-runtime-config-redis-endpoints.md` | `feature/057-runtime-config-redis-endpoints` | 055 |

```bash
uv run python scripts/worktree_tasks.py plan -f docs/technical/feature-053-parity-parallel.manifest.yaml
uv run python scripts/worktree_tasks.py prepare -f docs/technical/feature-053-parity-parallel.manifest.yaml
```

Worktrees root: `../master-ia-worktrees/`. SDK auto-runner not implemented — use Cursor agents per `INSTRUCTIONS.md` in each worktree.

### Parallel orchestration (wave 2)

**Goal:** Close Phase 1 (`feature-058`) then unlock Phase 2 (`feature-059` → parallel `060` + `061`).

| Task | Work item | Branch | Depends on (merged) | Parallel with |
| --- | --- | --- | --- | --- |
| 058 | `feature-058-rag-coherence-and-eval-gate.md` | `feature/058-rag-coherence-and-eval-gate` | 055, 057 on `main` | 054 (optional, separate track) |
| 054 | `feature-054-agentic-estimation-loop.md` | `feature/054-agentic-estimation-loop` | — | 058 (optional) |
| 059 | `feature-059-rag-query-reformulator-and-token-budget.md` | `feature/059-rag-query-reformulator-and-token-budget` | 058 | — (start after 058 merges) |
| 060 | `feature-060-rag-hallucination-gate.md` | `feature/060-rag-hallucination-gate` | 059 | 061 |
| 061 | `feature-061-advanced-retrieval-s10-pipeline.md` | `feature/061-advanced-retrieval-s10-pipeline` | 059 | 060 |

**Recommended wave 2a (parity-first):** implement `058` only on `main` (sequential). Optional **wave 2a′:** add `054` in a second worktree while `058` runs (`max_parallel: 2`).

**Wave 2b (after 058 merges):** manifest `feature-053-parity-parallel-wave2b.manifest.yaml` — add `059` only.

**Wave 2c (after 059 merges):** manifest `feature-053-parity-parallel-wave2c.manifest.yaml` — `060` + `061` in parallel.

```bash
# Wave 2a — plan + dry-run (parity + optional agentic)
uv run python scripts/worktree_tasks.py plan -f docs/technical/feature-053-parity-parallel-wave2.manifest.yaml
uv run python scripts/worktree_tasks.py prepare -f docs/technical/feature-053-parity-parallel-wave2.manifest.yaml --dry-run

# Parity-only worktree
uv run python scripts/worktree_tasks.py prepare -f docs/technical/feature-053-parity-parallel-wave2.manifest.yaml --only 058
```

Child work items **058–061** are written under `docs/work-items/`. **062–065** remain named-only until `/write-feature` before their wave.

## Pull Request

- **Merged (feature-056 slice):** https://github.com/povedica/master-ia-lidr/pull/48
- **Merged (feature-055 slice):** https://github.com/povedica/master-ia-lidr/pull/49
- **Merged (feature-057 slice):** https://github.com/povedica/master-ia-lidr/pull/50
- **Merged (feature-058 slice):** https://github.com/povedica/master-ia-lidr/pull/51
- One PR per child feature (`feature-056` … `feature-065`), not one monolithic PR.

---

## How to start

1. Phase 1 parity is **complete**. Continue Phase 2:

```text
/start-task docs/work-items/feature-059-rag-query-reformulator-and-token-budget.md
```

2. Optional Session 12 track in parallel (separate worktree):

```text
/start-task docs/work-items/feature-054-agentic-estimation-loop.md
```

3. After `feature-059` merges, run wave 2c in parallel (`060` + `061`):

```text
/start-task docs/work-items/feature-060-rag-hallucination-gate.md
/start-task docs/work-items/feature-061-advanced-retrieval-s10-pipeline.md
```

For the full program track:

```text
/start-task docs/work-items/feature-053-official-master-parity-alignment.md
```

Use the **Implementation Plan** section as the checklist; implement only the current child slice per `/start-task` invocation.
