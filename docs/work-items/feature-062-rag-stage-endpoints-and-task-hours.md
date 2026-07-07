# Feature: RAG Stage Endpoints and Task Hours (Phase 2 parity)

## Objective

Expose the RAG pipeline **one stage at a time** (official S09/S11 wizard contract) and add **per-task hours** estimation (official S10), plus **idempotency** on the full RAG estimate path:

1. Stateless stage routes under `POST /api/v1/estimate/rag/stages/*` reusing the same pure functions as `RagEstimationService` (no duplicated pipeline logic).
2. `POST /api/v1/estimate/rag/tasks/hours` — structure-only tasks → distance-weighted hours consensus from historical task chunks.
3. `Idempotency-Key` header on `POST /api/v1/estimate/rag` with Redis (or in-memory fallback) TTL 24h.

This is **Phase 2 parity** child slice **Step 8** of `docs/work-items/feature-053-official-master-parity-alignment.md`.

## Context

### Official reference

| Artifact | Official path | Behavior |
| --- | --- | --- |
| Stage router | `api/routers/estimate_stages.py` | reformulate → retrieve → assemble → structure → generate → verify |
| Task hours | `generation/rag/task_hours.py` + `api/routers/estimate_tasks.py` | Per-task k-NN + weighted consensus |
| Idempotency | `generation/rag/idempotency.py` | Redis + in-memory fallback, 24h TTL |

### `master-ia` fork choices

- Prefix `/api/v1/estimate/rag/stages/*` (not `/v1/estimate/stages/*`).
- Reuse existing modules: `rag_query_reformulator`, `RetrievalService` / `advanced_retrieve`, `rag_context_assembler`, `complete_structured`, `verify_citations`, `check_coherence`, `gate_estimate`.
- Auth: `require_estimate_key` + `conditional_rate_limit` (feature-056).
- Request correlation: `get_request_id` / `X-Request-ID` middleware (feature-056).
- Judge uses `complete_structured` (Instructor), not Responses API.
- **Augmentation** (`augment_chunks`, FR-10) is **out of scope** — assemble stage truncates only; `augment=false` fixed until a future slice.
- Stdlib logging with `extra={"request_id": ...}`.

### Parent roadmap

- Depends on: `feature-060` (hallucination gate on verify stage), `feature-061` (advanced retrieve optional on retrieve stage).
- Blocks: React RAG wizard (future), `feature-063` (multi-index improves retrieve stage routing).

### Handoff from feature-060 / feature-061 (merged on `main`)

- Hallucination: `gate_estimate()`, `HallucinationReport` — verify stage returns citation + hallucination without full pipeline.
- Advanced retrieval: `advanced_retrieve()`, `StageConfig`, presets A–D — retrieve stage accepts `preset` or inline `StageConfig`.
- Recommended regression:

```bash
uv run pytest tests/test_rag_hallucination_gate.py tests/test_rag_estimation_service.py tests/embedding_pipeline/test_advanced_retrieval.py -q
```

## Scope

### Includes

- Router `app/routers/rag_stages.py` with stages:
  - `POST .../stages/reformulate`
  - `POST .../stages/retrieve` (basic mode A–D or advanced `StageConfig`)
  - `POST .../stages/assemble` (truncate + context block; no augmentation)
  - `POST .../stages/structure` (structure-only LLM, no hours)
  - `POST .../stages/generate` (grounded generation + citation/coherence signals, no auto-retry)
  - `POST .../stages/verify` (citations + coherence + hallucination gate)
- Router `app/routers/rag_task_hours.py`: `POST .../tasks/hours`.
- Service `app/services/rag_task_hours.py`: `compose_task_search_text`, distance-weighted consensus, `estimate_all`.
- Service `app/services/rag_idempotency.py`: `IdempotencyStore` (Redis + in-memory).
- Schemas under `app/schemas/rag_stages.py`, `app/schemas/rag_task_hours.py`.
- Wire idempotency into `rag_estimations.py` before `RagEstimationService.estimate()`.
- Settings: `RAG_IDEMPOTENCY_TTL_SECONDS`, `TASK_HOURS_TOP_K`, `TASK_HOURS_DISTANCE_THRESHOLD`.
- Unit + endpoint tests (mocked LLM/embedder).
- `.env.example`, README, `docs/arquitectura-estimador-cag.html`.

### Excludes

- `augment_chunks` / edge-loading reorder (FR-10 — separate slice).
- Multi-index collections (`feature-063`) — task hours uses `chunk_type='historical_task'` filter on existing `chunks` table.
- React wizard UI.
- Structure-only mode on full `POST /api/v1/estimate/rag` orchestrator (stages only).
- Live LLM judge in default fast suite (`@pytest.mark.slow`).

## Functional Requirements

- **FR-01:** Each stage endpoint is **stateless** — caller passes prior stage outputs in the request body.
- **FR-02:** Stage handlers call the **same functions** as `RagEstimationService`; no copy-pasted pipeline logic in routers.
- **FR-03:** `reformulate` accepts `question` + optional `transcript`; returns `EstimationQuery` + `search_text`.
- **FR-04:** `retrieve` accepts `search_text`, mode or `StageConfig`, returns chunk rows with `collection` label.
- **FR-05:** `assemble` truncates to token budget and returns `context_block` + `kept_chunks` + token count.
- **FR-06:** `structure` returns modules/tasks **without hours** via structured LLM (`RagStructureResult` or equivalent).
- **FR-07:** `generate` returns estimate + `fabricated_source_ids` + coherence flag (no corrective retry loop).
- **FR-08:** `verify` returns `CitationReport` + `CoherenceReport` + `HallucinationReport` for a given estimate + chunks.
- **FR-09:** `tasks/hours` fills hours per task; `has_match=false` when nearest neighbor exceeds distance threshold.
- **FR-10:** Duplicate `Idempotency-Key` within TTL returns cached `RagEstimationResponse` without re-running pipeline.
- **FR-11:** Distinct keys run full pipeline; cache miss stores serialized response after success.
- **FR-12:** When `ESTIMATE_API_KEY` set, all new endpoints return 401 without key (feature-056).
- **FR-13:** Pipeline failures map to 502; validation to 422; embedder missing to 500.

## Technical Approach

### Module layout

```text
app/routers/rag_stages.py
app/routers/rag_task_hours.py
app/schemas/rag_stages.py
app/schemas/rag_task_hours.py
app/services/rag_task_hours.py
app/services/rag_idempotency.py
app/services/rag_structure_generator.py   # structure-only pass (new, thin)
app/routers/rag_estimations.py          # idempotency header
app/main.py                             # register routers
tests/test_rag_stages.py
tests/test_rag_task_hours.py
tests/test_rag_idempotency.py
tests/test_rag_estimation_endpoint.py   # idempotency integration
```

### Stage data flow

```text
reformulate → {query, search_text}
retrieve    → {chunks[], mode/config metadata}
assemble    → {context_block, kept_chunks[], token_count}
structure   → {modules[], tasks without hours}   # parallel path for task hours wizard
generate    → {estimate, fabricated_ids, coherent}
verify      → {citation_report, coherence_report, hallucination_report}
```

### Idempotency

- Header: `Idempotency-Key` (max 128 chars).
- Key prefix: `idempotency:rag-estimate:`.
- Store: `RagEstimationResponse.model_dump_json()` (or equivalent stable JSON).
- Backend: Redis when `REDIS_URL` set; else thread-safe in-memory dict (tests + single-process dev).

### Settings preview

```text
RAG_IDEMPOTENCY_TTL_SECONDS=86400
TASK_HOURS_TOP_K=5
TASK_HOURS_DISTANCE_THRESHOLD=0.45
```

## Acceptance Criteria

- [ ] **AC-01:** `POST .../stages/reformulate` returns `search_text` deterministic for fixture input (mocked reformulator).
- [ ] **AC-02:** `POST .../stages/retrieve` returns chunks; advanced preset D honored when requested.
- [ ] **AC-03:** `POST .../stages/assemble` never exceeds token budget in unit test.
- [ ] **AC-04:** `POST .../stages/verify` returns hallucination report without running reformulate/retrieve/generate (AC-13 from feature-053).
- [ ] **AC-05:** `POST .../tasks/hours` returns per-task hours with `has_match` flags (AC-14 from feature-053).
- [ ] **AC-06:** Duplicate `Idempotency-Key` returns identical body; LLM not called twice (mocked) (AC-15).
- [ ] **AC-07:** Missing estimate API key → 401 when `ESTIMATE_API_KEY` configured.
- [ ] **AC-08:** `uv run pytest` fast suite passes; slow tests opt-in.
- [ ] **AC-09:** `.env.example` documents new settings.
- [ ] **AC-10:** `docs/arquitectura-estimador-cag.html` shows stage routes + idempotency.

## Test Plan

### Unit tests

- `rag_task_hours`: consensus math, threshold no-match, search text composition.
- `rag_idempotency`: get/set/TTL expiry (memory backend); Redis with `fakeredis` if available.
- `rag_structure_generator`: mocked structured output.

### Endpoint tests

- Each stage: happy path + 422 validation.
- Verify stage: canned estimate + chunks → reports populated.
- Idempotency: two POSTs same key → one LLM call (mock).
- Security: 401 without API key.

### Regression

```bash
uv run pytest tests/test_rag_estimation_service.py tests/test_rag_hallucination_gate.py tests/test_retrieval_advanced_endpoint.py -q
```

## Verification

| Check | Command |
| --- | --- |
| Stage tests | `uv run pytest tests/test_rag_stages.py -q` |
| Task hours | `uv run pytest tests/test_rag_task_hours.py -q` |
| Idempotency | `uv run pytest tests/test_rag_idempotency.py tests/test_rag_estimation_endpoint.py -q` |
| Fast suite | `uv run pytest` |

**Not verified yet:** live Redis idempotency across workers; live task-hours retrieval quality on sparse corpus.

## Documentation Plan

| Artifact | Update |
| --- | --- |
| `.env.example` | Idempotency + task hours vars |
| `README.md` | Stage endpoints + idempotency header |
| `docs/technical/README.md` | Parity matrix rows for stages + task hours |
| `docs/arquitectura-estimador-cag.html` | Stage wizard flow |
| `feature-053` | Step 8 ✅ when merged |

## Implementation Plan

- [ ] **Step 1:** Stage request/response schemas + `rag_structure_generator` (pure/TDD).
- [ ] **Step 2:** `rag_stages` router — reformulate + assemble (no DB).
- [ ] **Step 3:** `rag_stages` — retrieve + generate + verify (mocked deps).
- [ ] **Step 4:** `rag_task_hours` service + `tasks/hours` endpoint.
- [ ] **Step 5:** `rag_idempotency` + wire into `rag_estimations`.
- [ ] **Step 6:** Docs + architecture HTML + feature-053 progress.

## Estimation

- Size: **L**
- Estimated time: **6–8 hours**
- Planned steps: **6**

## Implementation progress

- [x] Step 1: Stage/structure schemas + task-hours consensus (TDD)
- [x] Step 2: `rag_stages` router — reformulate, assemble, structure
- [x] Step 3: `rag_stages` — retrieve, generate, verify
- [x] Step 4: `rag_task_hours` service + `tasks/hours` endpoint
- [x] Step 5: `rag_idempotency` + `Idempotency-Key` on full RAG estimate
- [ ] Step 6: Docs + architecture HTML + feature-053 closure

## Pull Request

- Draft: https://github.com/povedica/master-ia-lidr/pull/55
- Branch: `feature/062-rag-stage-endpoints-and-task-hours`

## How to start

```text
/start-task docs/work-items/feature-062-rag-stage-endpoints-and-task-hours.md
```

Parent: `docs/work-items/feature-053-official-master-parity-alignment.md` Phase 2 Step 8.
Prerequisites: `feature-060`, `feature-061` merged to `main` ✅.
