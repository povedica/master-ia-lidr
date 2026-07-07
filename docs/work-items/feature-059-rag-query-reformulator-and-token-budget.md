# Feature: RAG Query Reformulator and Token Budget (Phase 2 parity)

## Objective

Implement the **first Phase 2 S10/S11 retrieval-prep stages** on the RAG path:

1. `query_reformulator` producing `EstimationQuery` from a free-text `question` or optional `transcript`.
2. `compose_search_text()` to build the retrieval query string (replacing raw `question` in `RetrievalService.retrieve()`).
3. `truncate_to_token_budget()` in context assembly using `tiktoken`.

Wire all three into `RagEstimationService` before generation, preserving existing retrieval modes A–D.

This is **Phase 2 parity** child slice **Step 5** of `docs/work-items/feature-053-official-master-parity-alignment.md`.

## Context

### Official reference

| Artifact | Official path | Behavior |
| --- | --- | --- |
| Query reformulator | `generation/rag/query_reformulator.py` | LLM or heuristic extraction of estimation intent from transcript |
| Search text | `compose_search_text()` | Merges reformulated facets into one retrieval string |
| Token budget | `context_assembler.py:truncate_to_token_budget()` | Caps assembled context to model budget |

### `master-ia` fork choices

- New module `app/services/rag_query_reformulator.py` (not `embedding_pipeline` — uses `complete_structured` or a lightweight LLM call).
- Extend `app/services/rag_context_assembler.py` for truncation; keep assembly pure where possible.
- Use Instructor + LiteLLM via existing `structured_llm_client` for reformulation (not Responses API).
- Optional `transcript` field on `RagEstimateRequest`; when present, reformulator runs; when absent, pass-through reformulation (question-only).
- Stdlib logging; settings-driven model via `REFORMULATION_MODEL` or runtime config stub.

### Parent roadmap

- Depends on: `feature-058` (coherence gate merged — stable RAG baseline).
- Blocks: `feature-060` (hallucination gate), `feature-061` (advanced retrieval).
- Parallel with: none until `feature-058` merges.

## Scope

### Includes

- `EstimationQuery` Pydantic model (search facets, component hints, sector filters as applicable).
- `reformulate_query(question, transcript?) -> EstimationQuery`.
- `compose_search_text(query: EstimationQuery) -> str`.
- `truncate_to_token_budget(text, max_tokens, encoding) -> str` in `rag_context_assembler.py`.
- Settings: `REFORMULATION_MODEL`, `RAG_CONTEXT_MAX_TOKENS` (or reuse `estimation_output_tokens_max` pattern).
- Wire into `RagEstimationService.estimate()` between request parsing and retrieval.
- Unit tests with mocked reformulator and deterministic truncation fixtures.
- `.env.example` + README.

### Excludes

- Hallucination gate (`feature-060`).
- Advanced multi-index retrieval (`feature-061`).
- Stage endpoints (`feature-062`).
- Augmentation / synthesis (`feature-053` FR-10, FR-22).
- Web RAG wizard UI.

## Functional Requirements

- **FR-01:** When only `question` is provided, reformulator returns a pass-through `EstimationQuery` equivalent to the question (no extra LLM call unless `REFORMULATION_ENABLED=true`).
- **FR-02:** When `transcript` is provided, reformulator extracts at least one search facet (mocked in tests; live path uses structured LLM).
- **FR-03:** `compose_search_text()` is deterministic given `EstimationQuery`.
- **FR-04:** Retrieval uses composed search text, not raw `question`.
- **FR-05:** Assembled context is truncated before prompt rendering; truncation preserves chunk boundaries (drop tail chunks, never mid-chunk).
- **FR-06:** Coherence + citation verification still run unchanged after generation (`feature-058` regression).
- **FR-07:** Layering: reformulator in `app/services`; truncation in `rag_context_assembler`; no reverse imports.

## Technical Approach

### Module layout

```text
app/services/rag_query_reformulator.py
app/schemas/estimation_query.py
app/services/rag_context_assembler.py    # extend: truncate_to_token_budget
app/services/rag_estimation_service.py
app/schemas/rag_estimation_response.py   # optional transcript on request
app/config.py
tests/test_rag_query_reformulator.py
tests/test_rag_context_assembler.py
tests/test_rag_estimation_service.py
```

### Pipeline order (after this feature)

```text
reformulate_query → compose_search_text → retrieve → assemble → truncate_to_token_budget
  → generate → verify_citations → check_coherence
```

### Settings preview

```text
REFORMULATION_ENABLED=false
REFORMULATION_MODEL=
RAG_CONTEXT_MAX_TOKENS=8000
```

## Acceptance Criteria

- [ ] **AC-01:** `compose_search_text()` unit-tested with fixture `EstimationQuery` objects.
- [ ] **AC-02:** Truncation drops excess chunks and never exceeds token budget in unit test with fixed encoding.
- [ ] **AC-03:** `RagEstimationService` calls reformulator + truncation in correct order (service test with mocks).
- [ ] **AC-04:** Optional `transcript` on request accepted by router; validation errors for empty strings.
- [ ] **AC-05:** Paraphrase query `q3-crm-paraphrase` retrieval P@5 improves vs raw question (document in eval note or skipped with `@pytest.mark.slow`).
- [ ] **AC-06:** `uv run pytest` fast suite passes; reformulator LLM tests marked `slow` if live.
- [ ] **AC-07:** `.env.example` documents new settings.

## Test Plan

### Unit tests

- Reformulator pass-through vs transcript path (mocked LLM).
- `truncate_to_token_budget` edge cases: empty, single chunk, over-budget.
- Service integration with fake retrieval + fake LLM.

### Regression

- `tests/test_rag_coherence.py`, `tests/test_rag_estimation_endpoint.py`.

## Verification

| Check | Command |
| --- | --- |
| Reformulator + assembler | `uv run pytest tests/test_rag_query_reformulator.py tests/test_rag_context_assembler.py -q` |
| RAG service | `uv run pytest tests/test_rag_estimation_service.py -q` |
| Fast suite | `uv run pytest` |

## Documentation Plan

| Artifact | Update |
| --- | --- |
| `.env.example` | Reformulation + token budget vars |
| `README.md` | Optional `transcript` on RAG estimate |
| `feature-053` | Phase 2 reformulator rows |

## Implementation Plan

- [ ] **Step 1:** `EstimationQuery` schema + `compose_search_text()` (pure, TDD).
- [ ] **Step 2:** `truncate_to_token_budget()` in context assembler (TDD).
- [ ] **Step 3:** Reformulator module + settings (mocked LLM tests).
- [ ] **Step 4:** Wire `RagEstimationService` + request schema `transcript` optional field.
- [ ] **Step 5:** Docs + `.env.example`.

## Estimation

- Size: **M–L**
- Estimated time: **4–6 hours**
- Planned steps: **5**

## Handoff from feature-058

`feature-058` merged (PR #51). RAG pipeline after generation is stable:

```text
retrieve → assemble → generate → verify_citations → check_coherence → (response)
```

**Do not regress:** `RagEstimationOutcome.coherence_report`, `coherence_summary` on `POST /api/v1/estimate/rag`, and `check_coherence()` after citations.

**Insert reformulator + token budget before retrieval:**

```text
reformulate → compose_search_text → retrieve → truncate_to_token_budget → assemble → generate → verify_citations → check_coherence
```

**First verification after wiring:**

```bash
uv run pytest tests/test_rag_coherence.py tests/test_rag_estimation_service.py tests/test_rag_estimation_endpoint.py -q
```

Settings already on `main`: `RAG_COHERENCE_ENABLED`, `RAG_COHERENCE_TOTAL_TOLERANCE`.

## Implementation progress

- [ ] Step 1: `EstimationQuery` schema + `compose_search_text()` (pure, TDD)
- [ ] Step 2: `truncate_to_token_budget()` in context assembler (TDD)
- [ ] Step 3: Reformulator module + settings (mocked LLM tests)
- [ ] Step 4: Wire `RagEstimationService` + optional `transcript` on request
- [ ] Step 5: Docs + `.env.example`

## Pull Request

_(URL recorded after first push.)_

## How to start

```text
/start-task docs/work-items/feature-059-rag-query-reformulator-and-token-budget.md
```

Parent: `docs/work-items/feature-053-official-master-parity-alignment.md` Phase 2 Step 5.
Prerequisite: `feature-058` merged to `main` ✅ (PR #51).
