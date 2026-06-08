# Feature: Structural JSON Chunker for Budgets

> Increment 2 of 5 for the minimal embedding pipeline (Session 07).
> Depends on: `feature-030` (schemas must exist). Independent of `feature-032`, `feature-033`, `feature-034`.

## Objective

Implement `JSONStructuralChunker` in `app/embedding_pipeline/chunker.py`: turn a list of `Budget` objects into a flat list of `Chunk` objects, one chunk per budget component, with parent-budget context embedded in the chunk text and a tiktoken-based `token_count`.

This is the only chunking strategy in scope: **structural** (one component = one chunk). No recursive, semantic, or fixed-size splitting.

## Context

- Schemas (`Budget`, `BudgetComponent`, `Chunk`) come from `feature-030` (`app/embedding_pipeline/schemas.py`).
- `tiktoken` was added as a dependency in `feature-030`.
- Logging in this repo uses stdlib `logging.getLogger(__name__)` with structured `extra={...}` (see `app/routers/estimations_v2.py`, `app/guardrails/llm_pipeline.py`). The exercise text says "structlog"; this repo has no `structlog` dependency and rule `06-error-handling-and-logging` is satisfied by stdlib + stable `extra` keys. **Use stdlib logging with `extra`** for consistency (architecture review, MEDIUM). Do not add `structlog`.

## Scope

### Includes
- `JSONStructuralChunker` class in `app/embedding_pipeline/chunker.py`.
- Public method `chunk(self, budgets: list[Budget]) -> list[Chunk]`.
- Token counting via `tiktoken.encoding_for_model("text-embedding-3-small")`.

### Excludes
- Any embedding / OpenAI call (Feature 032).
- FastAPI routes or CLI (Features 033/034).
- Alternative chunking strategies.
- Persisting chunks anywhere.

## Functional Requirements

For each `BudgetComponent` of each `Budget`, produce exactly one `Chunk`:

- `chunk_id` format: `{budget_id}::{component_id}` (e.g. `BUD-2024-014::AUTH-001`).
- `text` field, built with exactly this layout:

```text
[Project: {project_summary}] [Client sector: {sector} | Year: {year} | Main tech: {main_technology}]
Component: {component.name}
Description: {component.description}
Tech stack: {", ".join(component.tech_stack)}
Complexity: {component.complexity}
Estimated hours: {component.estimated_hours}
```

  - `{sector}` is `budget.client_metadata.sector`.
- `metadata` dict must include exactly these keys: `budget_id`, `component_id`, `client_sector`, `main_technology`, `year`, `complexity`, `estimated_hours`.
- `token_count`: number of tokens in `text` using the `text-embedding-3-small` encoding.
- The encoder is created once (e.g. in `__init__` or a cached helper), not per component.
- Log once per `chunk()` call at INFO: number of budgets processed and total chunks produced, e.g.
  `logger.info("chunker_completed", extra={"total_budgets": n, "total_chunks": m})`.

Edge cases:
- A budget with zero components contributes zero chunks (documented, allowed).
- Empty `budgets` list returns `[]` and still logs counts (0/0).

## Technical Approach

- `app/embedding_pipeline/chunker.py`:
  - `import logging`, `import tiktoken`, import schemas from `app.embedding_pipeline.schemas`.
  - `logger = logging.getLogger(__name__)`.
  - `class JSONStructuralChunker:` with `__init__` resolving the encoder via `tiktoken.encoding_for_model("text-embedding-3-small")`.
  - Private helper `_build_text(budget, component) -> str` for the exact layout.
  - Private helper `_build_metadata(budget, component) -> dict[str, object]`.
  - `chunk()` iterates budgets → components, builds `Chunk(...)`, counts tokens with `len(self._encoder.encode(text))`, appends, then logs totals.
- Pure, synchronous, no network. Deterministic output for the same input.

## Acceptance Criteria
- [x] AC-01: `JSONStructuralChunker().chunk(budgets)` returns `len == total components across all budgets`.
- [x] AC-02: Every `chunk.chunk_id` equals `f"{budget_id}::{component_id}"`.
- [x] AC-03: Every `chunk.text` matches the exact template (project/client header + 5 component lines).
- [x] AC-04: Every `chunk.metadata` contains exactly the 7 required keys with correct values.
- [x] AC-05: Every `chunk.token_count > 0` and equals the tiktoken count of `chunk.text`.
- [x] AC-06: The encoder is instantiated once per chunker, not per component.
- [x] AC-07: A budget with no components yields no chunks; empty input yields `[]`.
- [x] AC-08: One INFO log per `chunk()` call with `total_budgets` and `total_chunks` in `extra`.
- [x] AC-09: No OpenAI/network calls; module imports without API keys.

## Test Plan
- Unit tests (`tests/embedding_pipeline/test_chunker.py`):
  - Two budgets with multiple components each → assert total chunk count (AC-01).
  - Assert `chunk_id` format and metadata keys/values (AC-02, AC-04).
  - Assert `text` equals an expected string for a known fixture (AC-03).
  - Assert `token_count == len(encoder.encode(text))` and `> 0` (AC-05).
  - Empty list and zero-component budget cases (AC-07).
  - Use `caplog` to assert the completion log and its `extra` keys (AC-08).
- Integration tests: none.
- Manual checks: build 2 sample budgets and print resulting chunk count + first `chunk_id`.

## Verification
- **Verified:** `uv run pytest tests/embedding_pipeline/test_chunker.py` — 11 passed.
- **Verified:** `uv run pytest tests/embedding_pipeline/` — 22 passed (schemas + chunker).
- **Not verified:** manual REPL smoke (optional); embeddings, endpoint, CLI (features 032–034).

## Documentation Plan
- README: extend the embedding-pipeline subsection with the chunk text/metadata contract.
- Second Brain: note the structural chunking decision and the `{budget_id}::{component_id}` id scheme.

## Estimation

- Size: S
- Estimated time: 1.5 hours
- Planned steps: 5

## Implementation progress

- [x] Step 1: Add `tests/embedding_pipeline/test_chunker.py` with fixtures (RED).
- [x] Step 2: Implement `_build_text` and `_build_metadata`.
- [x] Step 3: Implement `chunk()` with single-encoder token counting and completion log.
- [x] Step 4: Run tests to green; verify edge cases.
- [x] Step 5: Update README + Second Brain note.

## Pull request

- WIP draft PR: https://github.com/povedica/master-ia-lidr/pull/26

## Implementation Plan
- [x] Step 1: Add `tests/embedding_pipeline/test_chunker.py` with fixtures (RED).
- [x] Step 2: Implement `_build_text` and `_build_metadata`.
- [x] Step 3: Implement `chunk()` with single-encoder token counting and completion log.
- [x] Step 4: Run tests to green; verify edge cases.
- [x] Step 5: Update README + Second Brain note.

## Repository commits (master-ia)

| SHA | Message |
|-----|---------|
| `192f9f7` | `docs(feature-031): add estimation and implementation progress tracking` |
| `dec250b` | `test(embedding-pipeline): add structural chunker contract tests (RED)` |
| `f669a0d` | `feat(embedding-pipeline): implement JSONStructuralChunker` |
| `55d5a46` | `docs(feature-031): document structural chunker contract and verification` |

## Learnings
- Token counting must reuse a single encoder instance; re-creating `encoding_for_model` per component is a measurable waste at scale.
- Keep the text template byte-for-byte stable: downstream embedding quality (Feature 034 sanity check) depends on consistent context formatting.
