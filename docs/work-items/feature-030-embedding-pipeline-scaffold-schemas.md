# Feature: Embedding Pipeline Scaffold and Pydantic Schemas

> Increment 1 of 5 for the minimal embedding pipeline (Session 07).
> Sibling work items: `feature-031` (chunker), `feature-032` (embedder), `feature-033` (ingest endpoint), `feature-034` (CLI cosine + sanity check).

## Objective

Create the `app/embedding_pipeline/` module skeleton and implement all Pydantic v2 data models in `schemas.py`, so later increments (chunker, embedder, endpoint, CLI) have a single, validated contract to build on. Add the only missing runtime dependency (`tiktoken`).

This increment ships **types and structure only**: no chunking, no embedding, no routes.

## Context

- The service lives under `app/` (FastAPI + Pydantic v2 + `pydantic-settings`). The exercise text references `servicio_ia/`; in this repo the package root is `app/`.
- Prior work (Session 06) produced normalized historical budget JSON. This feature only models that JSON; it does not read or pipe any files.
- Existing embedding code already exists for the semantic cache (`app/services/semantic_cache/openai_embeddings.py`, `embeddings.py`). The embedding pipeline is a **separate, isolated learning module**; it must not import or modify semantic-cache code.
- Pydantic v2 is the project standard (`app/schemas/*`). Reuse `BaseModel`, `Field`, and `model_config` patterns already used there.

### Budget JSON schema (simplified, authoritative for this feature)

```json
{
  "budget_id": "BUD-2024-014",
  "client_metadata": { "name": "FintechCorp", "sector": "finance", "country": "ES" },
  "project_summary": "Mobile banking API with OAuth 2.0 authentication",
  "main_technology": "ruby_on_rails",
  "year": 2024,
  "total_estimated_hours": 480,
  "components": [
    {
      "component_id": "AUTH-001",
      "name": "OAuth 2.0 authentication backend",
      "description": "Implementation of OAuth 2.0 flows with JWT session management",
      "tech_stack": ["ruby_on_rails", "postgresql", "redis"],
      "estimated_hours": 120,
      "complexity": "high",
      "dependencies": []
    }
  ]
}
```

## Scope

### Includes
- New package `app/embedding_pipeline/` with `__init__.py`.
- Empty stubs (with a `TODO` and a one-line docstring) for `chunker.py`, `embedder.py`, `router.py`.
- Fully implemented `app/embedding_pipeline/schemas.py`.
- New package `app/scripts/` with `__init__.py` and a `compare.py` stub (TODO).
- Add `tiktoken>=0.7.0` to `pyproject.toml` dependencies and update `uv.lock`.

### Excludes
- Any chunking, embedding, OpenAI calls, FastAPI routes, or CLI behavior (later increments).
- Vector DB persistence (Session 08).
- Touching existing routers, frontend, business backend, or semantic-cache code.
- Adding `numpy`, `scikit-learn`, or any ML library beyond `openai` (already present) and `tiktoken`.

## Functional Requirements

Implement these Pydantic v2 models in `app/embedding_pipeline/schemas.py`:

- `ClientMetadata`: `name: str`, `sector: str`, `country: str`.
- `BudgetComponent`: `component_id: str`, `name: str`, `description: str`, `tech_stack: list[str]`, `estimated_hours: int`, `complexity: str`, `dependencies: list[str]`.
- `Budget`: `budget_id: str`, `client_metadata: ClientMetadata`, `project_summary: str`, `main_technology: str`, `year: int`, `total_estimated_hours: int`, `components: list[BudgetComponent]`.
- `Chunk`: `chunk_id: str`, `text: str`, `metadata: dict[str, object]`, `token_count: int`.
- `EmbeddedChunk(Chunk)`: adds `embedding: list[float]` (extends `Chunk`).
- `IngestStats`: typed stats container with `total_budgets: int`, `total_chunks: int`, `total_tokens: int`, `estimated_cost_usd: float`.
  - Rationale: the exercise specifies a `stats: dict`; this repo prefers explicit Pydantic models over loose dicts (architecture review, MEDIUM). The JSON response still serializes to the exact required keys.
- `IngestRequest`: `budgets: list[Budget]`.
- `IngestResponse`: `chunks: list[EmbeddedChunk]`, `stats: IngestStats`.

Behavioral notes:
- `complexity` stays a free `str` for this increment (no enum); document that constraining it is a possible later refinement.
- `Chunk.metadata` stays a `dict` because keys are produced by the chunker (Feature 031); the required keys are documented there, not enforced here.
- Models must be importable as `from app.embedding_pipeline.schemas import Budget, Chunk, EmbeddedChunk, IngestRequest, IngestResponse`.

## Technical Approach

- One module `app/embedding_pipeline/schemas.py` with the models above; group them top-down (`ClientMetadata` → `BudgetComponent` → `Budget` → `Chunk` → `EmbeddedChunk` → `IngestStats` → `IngestRequest` → `IngestResponse`).
- Use `from __future__ import annotations` and explicit type hints, consistent with `app/schemas/*`.
- Stubs (`chunker.py`, `embedder.py`, `router.py`, `scripts/compare.py`) contain a module docstring and a `# TODO(feature-0NN): ...` line only; they must import cleanly.
- `pyproject.toml`: append `tiktoken>=0.7.0` to `[project].dependencies`. `openai>=1.60.0` is already present (exercise asks for `openai>=1.0.0`, already satisfied — do not downgrade). Run `uv sync` to refresh `uv.lock`.

## Acceptance Criteria
- [x] AC-01: `app/embedding_pipeline/__init__.py` exists and the package imports without error.
- [x] AC-02: `chunker.py`, `embedder.py`, `router.py` exist as importable stubs with a TODO marker.
- [x] AC-03: `app/scripts/__init__.py` and `app/scripts/compare.py` exist as importable stubs.
- [x] AC-04: `schemas.py` defines all 8 models (`ClientMetadata`, `BudgetComponent`, `Budget`, `Chunk`, `EmbeddedChunk`, `IngestStats`, `IngestRequest`, `IngestResponse`).
- [x] AC-05: `EmbeddedChunk` is a subclass of `Chunk` and adds only `embedding: list[float]`.
- [x] AC-06: All models instantiate from valid sample data matching the JSON schema above without validation errors.
- [x] AC-07: `EmbeddedChunk` requires `embedding`; constructing it without `embedding` raises `ValidationError`.
- [x] AC-08: `IngestResponse` serializes `stats` to JSON with keys `total_budgets`, `total_chunks`, `total_tokens`, `estimated_cost_usd`.
- [x] AC-09: `tiktoken>=0.7.0` is in `pyproject.toml` and `uv.lock` is updated; `openai` remains `>=1.60.0`.
- [x] AC-10: No imports from `app/services/semantic_cache/*` and no edits to existing routers/`main.py`.

## Test Plan
- Unit tests (`tests/embedding_pipeline/test_schemas.py`):
  - Build each model from valid sample data (AC-06).
  - Assert `EmbeddedChunk` rejects missing `embedding` (AC-07).
  - Assert `IngestResponse(...).model_dump()["stats"]` contains the 4 required keys (AC-08).
  - Assert `issubclass(EmbeddedChunk, Chunk)` (AC-05).
- Integration tests: none.
- Manual checks: `uv run python -c "from app.embedding_pipeline.schemas import Budget, Chunk, EmbeddedChunk, IngestRequest, IngestResponse"`.

## Verification
- Automated: `uv run pytest tests/embedding_pipeline/test_schemas.py` — **Verified** (11 passed, 2026-06-08).
- Manual: import check above; stub imports — **Verified**.
- `docs/arquitectura-estimador-cag.html`: **N/A** — increment 1 is types-only; no routes, orchestration, or env surface changes.
- Not verified yet: chunking, embedding, endpoint, CLI (later increments).

## Documentation Plan
- README: add a short "Embedding pipeline (Session 07)" subsection noting the module location and that increment 1 ships schemas only.
- Second Brain: session note capturing the schema contract and the decision to type `stats` and keep the module isolated from the semantic cache.

## Estimation

- Size: S
- Estimated time: 1.5 hours
- Planned steps: 6

## Implementation progress

- [x] Step 1: Package skeleton (`embedding_pipeline` + `scripts` stubs)
- [x] Step 2: Schema tests (RED)
- [x] Step 3: Implement `schemas.py` (GREEN)
- [x] Step 4: Add `tiktoken` dependency
- [x] Step 5: README + session note
- [x] Step 6: Final verification and acceptance sync

## Implementation Plan
- [x] Step 1: Create `app/embedding_pipeline/` package with `__init__.py` and the three stubs.
- [x] Step 2: Create `app/scripts/` package with `__init__.py` and `compare.py` stub.
- [x] Step 3: Implement the 8 models in `schemas.py`.
- [x] Step 4: Add `tiktoken>=0.7.0` to `pyproject.toml`, run `uv sync`, commit `uv.lock`.
- [x] Step 5: Add `tests/embedding_pipeline/test_schemas.py` and run the suite.
- [x] Step 6: Update README + Second Brain note.

## Retrospective (2026-06-08)

- **Process:** TDD honored — RED on missing `schemas.py`, then GREEN with 11 passing tests. Five focused commits on the feature branch.
- **Technical:** Reused Pydantic v2 patterns from `app/schemas/*`; module stays isolated from semantic cache.
- **Quality:** All AC-01–AC-10 met; no router or `main.py` changes.
- **Docs:** README subsection, session note at `learnings/docs/sesiones/sesion-07-embedding-pipeline-schemas.md`, architecture HTML N/A (types-only increment).

## Learnings
- Architecture review for this milestone flagged (HIGH) that routes belong in `app/routers/` and the embedder must be async — both handled in `feature-033` and `feature-032`, not here. This increment intentionally stays at the type layer.
- Prefer a typed `IngestStats` over a bare `dict` to match repo conventions while preserving the exact JSON keys the exercise verifies.

## Pull Request

- Merged: https://github.com/povedica/master-ia-lidr/pull/25

## Repository commits (master-ia)

| Commit | Summary |
|--------|---------|
| `013f403` | `docs(embedding-pipeline): add feature work items 030-034 for Session 07` |
| `acee4d5` | `feat(embedding-pipeline): add module skeleton and script stubs` |
| `6233314` | `test(embedding-pipeline): add schema contract tests (RED)` |
| `42997e7` | `feat(embedding-pipeline): implement Pydantic schemas for ingest contract` |
| `0c5bd0e` | `chore(deps): add tiktoken for embedding pipeline chunker` |
| `def7cea` | `docs(embedding-pipeline): document Session 07 increment 1` |
| `34f0eb6` | `docs(feature-030): record implementation commit hashes` |
| `75dd33c` | `docs(feature-030): complete retrospective and mark PR merged` |
