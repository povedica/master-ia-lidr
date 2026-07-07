# Feature: Advanced Retrieval S10 Pipeline (Phase 2 parity)

## Objective

Port official **Session 10 advanced retrieval** into `master-ia`:

1. `StageConfig` dataclass controlling query transform, routing, fusion, rerank, temporal decay.
2. `advanced_retrieve()` orchestrating multi-stage retrieval over the existing `chunks` table (single collection for now).
3. HTTP endpoint `POST /api/v1/retrieval/advanced` returning chunks with provenance labels.
4. Map `StageConfig` dimensions to existing modes A–D where possible (backward compatibility).

This is **Phase 2 parity** child slice **Step 7** of `docs/work-items/feature-053-official-master-parity-alignment.md`.

## Context

### Official reference

| Artifact | Official path | Behavior |
| --- | --- | --- |
| Advanced pipeline | `generation/rag/retrieval/advanced_pipeline.py` | StageConfig-driven retrieval |
| Collections | `retrieval/collections.py` | Multi-index routing (budgets / transcripts / technical_docs) |
| Query transform | `retrieval/query_transform.py` | Decomposition / expansion |
| Router | `retrieval/router.py` | Collection routing rules |
| Temporal decay | `retrieval/temporal.py` | Recency weighting |

### `master-ia` fork choices

- New modules under `app/embedding_pipeline/` (retrieval domain): `advanced_retrieval.py`, `stage_config.py`, optional `query_transform.py`, `retrieval_router.py`, `temporal_decay.py`.
- **Single `chunks` table** in this slice; `collection` discriminator deferred to `feature-063` (return `collection="budgets"` label for all rows).
- Reuse `RetrievalService`, hybrid RRF, and `Reranker` primitives — compose, do not duplicate fusion math.
- Honor `feature-057` runtime retrieval config for rerank toggle.
- API key auth from `feature-056` on new endpoint when keys configured.

### Parent roadmap

- Depends on: `feature-059` (composed search text — advanced pipeline accepts same input contract).
- Blocks: `feature-062` (stage retrieve endpoint), `feature-063` (multi-index).
- Parallel with: `feature-060` after `feature-059` merges (`mutex_group: rag-pipeline` vs `rag-quality`).

## Scope

### Includes

- `StageConfig` dataclass + validation.
- `advanced_retrieve(session, query, config, ...)` async function.
- Router stub: all queries → `budgets` collection until `feature-063`.
- Optional query transform behind `QUERY_TRANSFORM_ENABLED`.
- `POST /api/v1/retrieval/advanced` request/response schemas.
- Unit tests ported from official `test_advanced_pipeline.py` patterns (mocked DB/embedder).
- Eval note mapping modes A–D ↔ `StageConfig` presets.
- `.env.example` + README.

### Excludes

- Multi-index migrations (`feature-063`).
- RAG orchestrator wiring advanced path by default (optional follow-up flag `RETRIEVAL_ROUTING_ENABLED`).
- Temporal decay live data requirements (stub/no-op OK when metadata missing).
- Web UI.

## Functional Requirements

- **FR-01:** `StageConfig` exposes at least: `search_mode` (vector|hybrid), `rerank`, `query_transform`, `routing_enabled`, `fusion` (rrf|round_robin), `temporal_decay`.
- **FR-02:** `advanced_retrieve()` returns rows with `collection` label and fusion scores.
- **FR-03:** Preset configs `mode_a` … `mode_d` match existing `RetrievalService` behavior in integration test.
- **FR-04:** `POST /api/v1/retrieval/advanced` returns 401 without API key when `RETRIEVAL_API_KEY` set.
- **FR-05:** Runtime `rerank_enabled` override from Redis affects advanced path.
- **FR-06:** Layering: router → `advanced_retrieve` → repositories; no service imports from routers.

## Technical Approach

### Module layout

```text
app/embedding_pipeline/stage_config.py
app/embedding_pipeline/advanced_retrieval.py
app/embedding_pipeline/query_transform.py      # optional stub
app/embedding_pipeline/retrieval_router.py
app/embedding_pipeline/temporal_decay.py
app/routers/retrieval_advanced.py              # or extend retrieval.py
app/schemas/retrieval_advanced.py
tests/embedding_pipeline/test_advanced_retrieval.py
tests/test_retrieval_advanced_endpoint.py
```

### Mode mapping (feature-053)

| `master-ia` mode | `StageConfig` preset |
| --- | --- |
| A | vector, rerank=false, routing off |
| B | hybrid, rerank=false |
| C | vector, rerank=true |
| D | hybrid, rerank=true |

### Settings preview

```text
RETRIEVAL_ROUTING_ENABLED=false
QUERY_TRANSFORM_ENABLED=false
RETRIEVAL_TEMPORAL_DECAY_ENABLED=false
```

## Acceptance Criteria

- [x] **AC-01:** `advanced_retrieve()` unit tests with mocked repositories pass.
- [x] **AC-02:** Mode A–D presets produce same chunk ordering as `RetrievalService` for fixture (integration test).
- [x] **AC-03:** `POST /api/v1/retrieval/advanced` returns chunks with `collection` field.
- [x] **AC-04:** API key enforcement when configured.
- [x] **AC-05:** `uv run pytest tests/embedding_pipeline/test_advanced_retrieval.py tests/test_retrieval_advanced_endpoint.py -q` passes.
- [x] **AC-06:** `.env.example` documents S10 flags.

## Test Plan

### Unit tests

- StageConfig validation.
- Fusion and routing with fake rows.
- Query transform stub passthrough.

### API tests

- TestClient + mocked retrieval backend.
- Security test with `RETRIEVAL_API_KEY`.

## Verification

| Check | Command | Result |
| --- | --- | --- |
| Advanced retrieval | `uv run pytest tests/embedding_pipeline/test_advanced_retrieval.py tests/embedding_pipeline/test_advanced_retrieval_stubs.py tests/embedding_pipeline/test_stage_config.py -q` | **18 passed** |
| Endpoint | `uv run pytest tests/test_retrieval_advanced_endpoint.py -q` | **5 passed** |
| Security regression | `uv run pytest tests/test_api_security.py -q` | **10 passed** |
| Feature bundle | `uv run pytest tests/embedding_pipeline/test_advanced_retrieval.py tests/test_retrieval_advanced_endpoint.py -q` | **16 passed** |
| Fast suite | `uv run pytest` | **759 passed**, 2 failed (`test_config` defaults — local worktree `.env` bleeds `DATABASE_URL` / `RETRIEVAL_RERANK_ENABLED`; not feature regression) |

## Eval mapping (modes A–D ↔ StageConfig presets)

| Production mode | `preset` | `search_mode` | `rerank` | `fusion` |
| --- | --- | --- | --- | --- |
| A | `"A"` | `vector` | `false` | `rrf` |
| B | `"B"` | `hybrid` | `false` | `rrf` |
| C | `"C"` | `vector` | `true` | `rrf` |
| D | `"D"` | `hybrid` | `true` | `rrf` |

Offline parity: `test_advanced_presets_match_retrieval_service_ordering` in `tests/embedding_pipeline/test_advanced_retrieval.py`.

## Documentation Plan

| Artifact | Update |
| --- | --- |
| `.env.example` | S10 retrieval flags | ✅ |
| `README.md` | Advanced retrieval endpoint | ✅ |
| `feature-053` | Phase 2 advanced retrieval row | ✅ |
| `docs/technical/README.md` | §25d advanced retrieval | ✅ |

## Implementation Plan

- [x] **Step 1:** `StageConfig` + presets for modes A–D (TDD).
- [x] **Step 2:** `advanced_retrieve()` core with hybrid + rerank reuse.
- [x] **Step 3:** Router + query transform stubs.
- [x] **Step 4:** HTTP endpoint + schemas.
- [x] **Step 5:** Docs + eval mapping note.

## Estimation

- Size: **L**
- Estimated time: **6–8 hours**
- Planned steps: **5**

## Handoff from feature-059

`feature-059` wires retrieval prep before generation:

```text
reformulate_query → compose_search_text → retrieve → assemble → truncate_assembled_context → generate → verify_citations → check_coherence
```

**Advanced retrieval is a parallel retrieval path** (not wired into `RagEstimationService` by default in this slice):

- Accept the same composed search text contract as `RetrievalService.retrieve()`.
- Reuse hybrid RRF and `Reranker` primitives; do not duplicate fusion math.
- Honor `feature-057` runtime retrieval config for rerank toggle.

**First verification after wiring:**

```bash
uv run pytest tests/embedding_pipeline/test_advanced_retrieval.py tests/test_retrieval_advanced_endpoint.py -q
```

## Implementation progress

- [x] Step 1: `StageConfig` + presets for modes A–D (TDD)
- [x] Step 2: `advanced_retrieve()` core with hybrid + rerank reuse
- [x] Step 3: Router + query transform stubs
- [x] Step 4: HTTP endpoint + schemas
- [x] Step 5: Docs + eval mapping note

## Handoff from feature-061

**Shipped interfaces**

- `POST /api/v1/retrieval/advanced` — `AdvancedRetrievalRequest` (`preset` or `config`, optional `recall_k` / `top_k_final`).
- `advanced_retrieve(session, query, config, …)` — core orchestrator in `app/embedding_pipeline/advanced_retrieval.py`.
- `StageConfig` + presets `mode_a_preset()` … `mode_d_preset()` in `app/embedding_pipeline/stage_config.py`.
- Stubs: `retrieval_router.route_collection`, `query_transform.transform_query`, `temporal_decay.apply_temporal_decay`.
- Settings: `RETRIEVAL_ROUTING_ENABLED`, `QUERY_TRANSFORM_ENABLED`, `RETRIEVAL_TEMPORAL_DECAY_ENABLED`.

**Contracts**

- Input query: same composed search text contract as `RetrievalService.retrieve()`.
- Output rows: include `collection` (stub `"budgets"`); fusion/rerank scores mirror production retrieval.
- Auth: `require_retrieval_key` (shared with `POST /api/v1/retrieval`).
- Runtime rerank: `get_effective_settings` + Redis override from feature-057.

**Verified**

- 18 unit tests across `test_stage_config`, `test_advanced_retrieval`, `test_advanced_retrieval_stubs`.
- 5 endpoint tests + 2 security tests for advanced path.
- Preset A–D ordering parity vs `RetrievalService` on shared fixtures.

**Not verified / residual risk**

- `fusion="round_robin"` raises `ValueError` (RRF only in this slice).
- Multi-index routing (`feature-063`) and live query transform/decay not implemented.
- Advanced path not wired into `RagEstimationService` (parallel path only).
- Full `uv run pytest`: 2 `test_config` defaults fail when worktree `.env` pollutes process env.

**Recommended first tests for feature-062 / feature-063**

```bash
uv run pytest tests/embedding_pipeline/test_advanced_retrieval.py tests/test_retrieval_advanced_endpoint.py -q
```

## Repository commits (master-ia)

| Step | Commit | Summary |
| --- | --- | --- |
| 1 | f72f50b | `StageConfig` dataclass + mode A–D presets with validation and unit tests |
| 2 | f690f9f | `advanced_retrieve()` core composing hybrid RRF, rerank, and `collection` labels |
| 3 | 631586e | Router, query-transform, and temporal-decay stubs wired into `advanced_retrieve` |
| 4 | 406dec4 | `POST /api/v1/retrieval/advanced` endpoint, schemas, security, and parity tests |
| 5 | *(this commit)* | Docs (`.env.example`, README, technical §25d, feature-053) + eval mapping |

## Pull Request

- Draft PR: https://github.com/povedica/master-ia-lidr/pull/53
- Branch: `feature/061-advanced-retrieval-s10-pipeline`
- Worktree: `../master-ia-worktrees/feature-061-advanced-retrieval-s10-pipeline`
- Parallel manifest: `docs/technical/feature-053-parity-parallel-wave2b.manifest.yaml`

## How to start

```text
/start-task docs/work-items/feature-061-advanced-retrieval-s10-pipeline.md
```

Parent: `docs/work-items/feature-053-official-master-parity-alignment.md` Phase 2 Step 7.
Prerequisite: `feature-059` merged to `main`.
