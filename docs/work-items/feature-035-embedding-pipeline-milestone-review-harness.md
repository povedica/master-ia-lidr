# Feature: Embedding Pipeline Milestone Review, Hardening & Upstream-Ready Contracts

> Consolidation work item for Session 07 (features **030–034**) plus improvements identified in the 2026-06-08 architecture comparison with `ai-engineering/estimator/app/ingestion/`.
> Depends on: `feature-030` … `feature-034` (all merged).
> **Scope change (2026-06-08):** expanded from a tests-only harness to include pipeline hardening, upstream-ready contracts, lightweight ingestion primitives, and offline CLI tooling — while keeping the module isolated from `semantic_cache` and deferring Session 08 persistence.

## Objective

Deliver one coherent increment that:

1. **Verifies** the Session 07 milestone end to end (schemas → chunker → embedder → ingest → CLI) with a repeatable harness, fixtures, API-collection entry, and optional real-key smoke tests.
2. **Hardens** known weaknesses from architecture reviews and the estimator comparison (dead stub, embedder client churn, tiktoken/model drift).
3. **Prepares upstream ingestion** without copying estimator wholesale: a minimal filesystem → `Budget` path, a RAG-ready intermediate `Document` contract, and markdown-enriched chunk text — all **wired into the existing ingest orchestration**, not as orphan modules.
4. **Adds offline CLI tools** (preflight, architecture decision, fixture inspect) for learning and ops readiness.
5. **Closes documentation gaps** (`docs/technical/README.md`, cross-pipeline comparison, architecture HTML).

**Design principle (from estimator anti-pattern review):** every new module introduced here must appear in at least one orchestrated path (HTTP ingest, a CLI, or a test). No “documented but unwired” layers (contrast: estimator’s `cleaning/` and `pii/` exist but are not called by `ingest_source()`).

## Context

### Session 07 baseline (master-ia)

- Milestone implemented and merged (PRs #25–#30). `uv run pytest tests/embedding_pipeline/` — 47 passing tests (2026-06-08).
- Flow today: inline `IngestRequest.budgets` → `JSONStructuralChunker.chunk()` → `OpenAIEmbedder.embed_many()` → `IngestResponse`.
- Strengths to **keep**: component-level chunking (finer than estimator’s 1-doc-per-budget), async embedder with batching/retry/cost stats, 47 offline tests, explicit isolation from `app/services/semantic_cache/*`.

### Estimator comparison (2026-06-08)

Reference repo: `/Users/pablo.poveda/CodeProjects/ai-engineering/estimator/app/ingestion/`.

| Dimension | master-ia (030–034) | estimator `ingestion/` | Action in this feature |
|-----------|---------------------|------------------------|------------------------|
| Upstream ingest | Inline JSON POST only | Catalog → loader → parser → `Document` | Add **minimal** loader + parser → `Budget[]` (no Postgres jobs) |
| Intermediate contract | `Chunk` only | `Document` + rich `DocumentMetadata` | Add `PipelineDocument` before chunking |
| Chunk text | Flat prose template | Markdown with `##` sections | Evolve chunker to markdown sections (keep 1 chunk/component) |
| Embedding | Full pipeline | Not in ingestion | **Keep** master-ia embedder as canonical |
| Jobs async + DB | No | 202 + poll | **Exclude** until Session 08 persistence |
| PII / Pandera cleaning | No | Modules exist, unwired | **Exclude** (avoid orphan modules); document as Session 08+ |
| Cost in API | Yes (`IngestStats`) | No | **Keep** |
| Ops CLIs | `compare.py` only | preflight, inspect, architecture | Add adapted offline CLIs |
| Logging | stdlib + `extra` | structlog | **Keep** stdlib (repo rule 06) |

### Known gaps to close in this feature

- No cross-increment milestone e2e test or shared multi-budget fixture.
- `docs/technical/README.md` missing embedding pipeline section.
- `conftest.py` `SAMPLE_CHUNK["chunk_id"]` uses single `:` instead of `::`.
- Dead stub `app/embedding_pipeline/router.py` (TODO resolved in feature-033).
- `OpenAIEmbedder` creates `AsyncOpenAI` per batch (`embedder.py:69`).
- Chunker hardcodes tiktoken model; settings allow `embedding_pipeline_model` override → token/cost drift.

## Scope

### Includes

#### A. Milestone verification harness
- `tests/embedding_pipeline/fixtures/sample_budgets.json` (≥2 budgets, ≥3 components, optional zero-component budget).
- `tests/embedding_pipeline/test_milestone_e2e.py` — offline e2e with fake embedder + real chunker (E2E-01..E2E-08).
- Optional `@pytest.mark.slow` smoke tests (SMOKE-01/SMOKE-02); deselected by default.
- `api-collection/Estimador CAG/embeddings/Ingest Budgets.yml` + `folder.yml`.
- Reviewer checklist (below) + README milestone-verification recipe.

#### B. Pipeline hardening
- Remove `app/embedding_pipeline/router.py` stub; add one-line pointer in `app/embedding_pipeline/__init__.py` if needed (`canonical route: app/routers/embeddings.py`).
- Reuse one `AsyncOpenAI` client per `OpenAIEmbedder` instance (lazy init after API-key check).
- Derive chunker tiktoken encoder from `settings.embedding_pipeline_model` (inject `Settings` into `JSONStructuralChunker` or pass model string via factory `get_chunker(settings)`); document fallback when model unknown to tiktoken.

#### C. Intermediate `PipelineDocument` contract
- New models in `app/embedding_pipeline/schemas.py` (or `documents.py` if schemas grows too large):
  - `PipelineDocumentMetadata`: `source_name`, `source_version`, `ingested_at`, `lineage: list[str]`, `location: str`, `extra: dict[str, object]`; optional `sensitivity_access_level: str = "internal"` (no PII pipeline yet — field reserved for Session 08).
  - `PipelineDocument`: `id: str`, `text: str`, `metadata: PipelineDocumentMetadata`.
- `BudgetToDocumentAdapter` (pure function or small class in `app/embedding_pipeline/adapters.py`): maps `Budget` → one `PipelineDocument` per component (text = current flat template **or** markdown — see D). Stable `id` = `{budget_id}::{component_id}`.
- Chunker refactored to accept either `list[Budget]` (backward compatible) or internally: `Budget[]` → `PipelineDocument[]` → `Chunk[]`. Public API remains `chunk(budgets: list[Budget]) -> list[Chunk]`; metadata on `Chunk` gains optional lineage fields copied from `PipelineDocumentMetadata`.

#### D. Markdown-enriched chunk text
- Evolve `JSONStructuralChunker._build_text()` to render **markdown sections** (estimator-inspired, component-granular):

```markdown
## Project context
- Summary: {project_summary}
- Sector: {sector} | Year: {year} | Main tech: {main_technology}

## Component: {component.name}
{component.description}

### Tech stack
{comma-separated tech_stack}

### Estimate
- Complexity: {complexity}
- Hours: {estimated_hours}
```

- **Stability rule:** update `tests/embedding_pipeline/test_chunker.py` expected strings and re-run sanity check guidance in `SANITY_CHECK.md` (note template change date; re-measure optional via `@pytest.mark.slow`).
- Keep `chunk_id` format `{budget_id}::{component_id}` unchanged.

#### E. Lightweight upstream ingestion (wired, minimal)
- `app/embedding_pipeline/loaders/filesystem.py`: `FileSystemLoader.iter_budget_files(directory: Path) -> Iterator[Path]` — yields `*.json` files only; no catalog YAML yet.
- `app/embedding_pipeline/parsers/budget_json.py`: `parse_budget_file(path: Path) -> Budget` — validates against existing `Budget` schema; raises clear errors on invalid JSON/schema.
- `app/embedding_pipeline/parsers/registry.py`: minimal registry mapping `"json"` → parser (Protocol + one implementation); extensible for future `txt` without changing HTTP contract.
- New optional HTTP query or body field **not** required in this increment — instead wire via CLI and tests:
  - `app/scripts/ingest_from_dir.py`: `python -m app.scripts.ingest_from_dir --dir path/to/budgets/` loads files → `Budget[]` → existing chunk+embed path (reuse `OpenAIEmbedder` + print stats or write JSON lines to stdout). Requires `OPENAI_API_KEY` for embed step; supports `--dry-run` (chunk only, no API).
- E2E test: load fixture directory → parse → chunk → assert chunk count (offline, no embed).

#### F. Offline CLI tools (under `app/scripts/`, Docker-safe)
- `app/scripts/preflight_embedding_pipeline.py`: checks `OPENAI_API_KEY` present (masked), settings load, tiktoken encoder resolves, imports clean, optional ping to OpenAI embeddings with `@pytest.mark.slow`-style opt-in flag `--live` (default off).
- `app/scripts/architecture_decision.py`: offline CAG vs RAG vs Hybrid recommendation (adapt logic from estimator `ingestion/architecture.py` — token budget heuristics, no FastAPI). Document as learning artifact in README.
- `app/scripts/inspect_fixtures.py`: scan a directory, print file count, valid/invalid budget JSON counts, total components — facts only (like estimator `catalog/inspect.py`).

#### G. Documentation
- `README.md`: milestone verification + new CLIs + `--dry-run` ingest-from-dir.
- `docs/technical/README.md`: embedding module, ingest route, env vars, new scripts, `PipelineDocument` contract.
- `docs/arquitectura-estimador-cag.html`: update § Pipeline embeddings with upstream loader/parser box, markdown chunk template, comparison note vs estimator ingestion.
- `docs/work-items/adr-NNN-embedding-pipeline-vs-estimator-ingestion.md` **or** a subsection in feature-034 consolidated learnings — short ADR: why two stages, what we adopted, what we deferred.
- Second Brain session note: milestone harness + hardening + comparison outcomes.

### Excludes
- Vector DB persistence, embedding storage, retrieval API (Session 08).
- Full YAML data catalog with `include|review|exclude`, quality scores, Postgres job polling (Session 08+; reference design only in ADR).
- PII detection/pseudonymization (Presidio), pandas/Pandera cleaning — do not add unwired modules.
- `structlog` migration.
- Merging `OpenAIEmbedder` with `semantic_cache/openai_embeddings.py` (isolation preserved until a third consumer exists).
- numpy / scikit-learn / new runtime deps beyond existing `tiktoken`, `openai`.
- Breaking HTTP contract: `POST /api/v1/embeddings/ingest` body shape stays `IngestRequest`; new upstream path is CLI-first.

## Functional Requirements

### A. Milestone harness

**Fixture**
- `sample_budgets.json`: valid `IngestRequest`; ≥2 budgets; ≥3 components total; ≥1 budget with 2+ components; ≥1 budget with 0 components (edge case).

**Offline e2e (`test_milestone_e2e.py`, fake embedder)**
- E2E-01: `POST /api/v1/embeddings/ingest` → `200`.
- E2E-02: `len(chunks) == total components`.
- E2E-03: `stats.total_budgets`, `stats.total_chunks`, tokens/cost from embedder.
- E2E-04: every `chunk_id` matches `{budget_id}::{component_id}`; metadata has 7 required keys (+ optional lineage if populated).
- E2E-05: embeddings length 1536; order preserved.
- E2E-06: stats not recomputed in router.
- E2E-07: empty `budgets` and zero-component budget paths.
- E2E-08: real `JSONStructuralChunker` (only embedder faked).

**Slow smoke (`@pytest.mark.slow`)**
- SMOKE-01: real key ingest of fixture → 200, correct counts, dim 1536.
- SMOKE-02: `compare.main([...])` exit 0, similarity in valid range.

**API collection**
- `embeddings/Ingest Budgets.yml` POST `{{baseUrl}}/api/v1/embeddings/ingest`.

### B. Hardening

- HARD-01: `app/embedding_pipeline/router.py` removed; no broken imports.
- HARD-02: `OpenAIEmbedder` uses one lazy `AsyncOpenAI` client per instance; existing embedder tests pass (may need to assert client reuse via mock call count).
- HARD-03: `JSONStructuralChunker` token encoder uses `settings.embedding_pipeline_model` (default `text-embedding-3-small`); `get_chunker(settings)` in `app/routers/embeddings.py` updated accordingly.
- HARD-04: If tiktoken cannot resolve the configured model, log warning and fall back to `cl100k_base` or `text-embedding-3-small` with documented behavior in README.

### C. `PipelineDocument` contract

- DOC-01: `PipelineDocument` and `PipelineDocumentMetadata` defined with `extra="forbid"` on metadata (Pydantic v2).
- DOC-02: `BudgetToDocumentAdapter` produces one document per component; `id` equals future `chunk_id` without `::` duplication logic in two places (single helper `make_component_id(budget_id, component_id) -> str`).
- DOC-03: Chunker uses adapter internally; `Chunk.metadata` includes `source_name`, `source_version`, `location` when provided (defaults for inline HTTP ingest: `source_name="inline"`, `source_version="api"`, `location=""`).

### D. Markdown chunk text

- MD-01: `_build_text` output matches the markdown section template above (exact headings and field labels stable for tests).
- MD-02: All chunker unit tests updated; token counts may change — assert relative consistency (`token_count > 0`, matches tiktoken of rendered text).
- MD-03: `SANITY_CHECK.md` adds a note that chunk template changed in feature-035; optional re-measurement documented, not required for AC.

### E. Lightweight upstream ingestion

- UP-01: `FileSystemLoader` yields only `*.json` under a given directory (non-recursive or one level deep — pick one, document it; default: non-recursive).
- UP-02: `parse_budget_file` returns `Budget`; invalid files raise `BudgetParseError` with path in message.
- UP-03: `ingest_from_dir.py --dir D --dry-run` prints chunk count and first `chunk_id` without OpenAI; without `--dry-run` runs embed and prints `IngestStats`-shaped summary to stdout.
- UP-04: Test loads `tests/embedding_pipeline/fixtures/budget_files/*.json` (split single budgets from combined fixture if needed) → parse all → chunk → assert total component count.

### F. CLI tools

- CLI-01: `preflight_embedding_pipeline.py` exit 0 when settings OK; exit 1 with clear stderr when key missing (unless `--skip-key-check`).
- CLI-02: `architecture_decision.py` accepts corpus token estimate + refresh days via args; prints `CAG | Hybrid | RAG` recommendation.
- CLI-03: `inspect_fixtures.py` prints valid/invalid file counts for a directory.

### G. Documentation

- DOCG-01: `docs/technical/README.md` updated (module, route, env vars, scripts).
- DOCG-02: Architecture HTML and ADR/comparison note published.

## Technical Approach

### Module layout (target)

```text
app/embedding_pipeline/
├── schemas.py              # existing + PipelineDocument*
├── adapters.py             # BudgetToDocumentAdapter, make_component_id
├── chunker.py              # markdown text, settings-aware tiktoken
├── embedder.py             # single AsyncOpenAI client
├── loaders/
│   └── filesystem.py
├── parsers/
│   ├── protocol.py
│   ├── registry.py
│   └── budget_json.py
└── SANITY_CHECK.md

app/routers/embeddings.py   # get_chunker(settings)
app/scripts/
├── compare.py                # unchanged behavior
├── ingest_from_dir.py        # new
├── preflight_embedding_pipeline.py
├── architecture_decision.py
└── inspect_fixtures.py
```

### Orchestration paths (everything wired)

| Path | Flow |
|------|------|
| HTTP ingest | `IngestRequest` → chunker (→ adapter internally) → embedder → response |
| ingest_from_dir CLI | loader → parser → `Budget[]` → same chunker → embedder (or dry-run stop after chunk) |
| Milestone e2e test | fixture JSON → HTTP → fake embedder |
| Upstream unit test | fixture files → loader → parser → chunker (offline) |

### Dependency injection

- Update `get_chunker` signature to `get_chunker(settings: Annotated[Settings, Depends(get_settings)]) -> JSONStructuralChunker`.
- Tests override settings via existing patterns or env in `conftest.py`.

### Estimator patterns **not** copied (document in ADR)

- Postgres `ingestion_jobs` + 202/poll — defer until vectors persist.
- Presidio/pseudonymizer — defer; do not ship unwired.
- Sync work inside `BackgroundTasks` — master-ia ingest stays async-await in handler.
- Catalog frozen at startup with `@lru_cache` — if catalog added later, use explicit reload or mtime check.

### Real APIs (do not invent)

- `JSONStructuralChunker.chunk`, `OpenAIEmbedder.embed_many` / `embed_one`, `IngestRequest` / `IngestResponse`, `compare.cosine_similarity`, FastAPI `dependency_overrides`.

## Acceptance Criteria

### Milestone harness
- [ ] AC-01: `sample_budgets.json` + conftest fixture exist; ≥2 budgets, ≥3 components.
- [ ] AC-02: `test_milestone_e2e.py` passes E2E-01..E2E-08 offline.
- [ ] AC-03: `@pytest.mark.slow` smoke tests exist and are deselected by default.
- [ ] AC-04: API-collection `embeddings/Ingest Budgets.yml` + `folder.yml` exist.

### Hardening
- [ ] AC-05: Dead `router.py` stub removed; package imports cleanly.
- [ ] AC-06: Single `AsyncOpenAI` client per embedder instance; embedder tests green.
- [ ] AC-07: Chunker encoder driven by `embedding_pipeline_model`; chunker + router tests green.

### Contracts & chunk text
- [ ] AC-08: `PipelineDocument` / `PipelineDocumentMetadata` defined and used by adapter.
- [ ] AC-09: Markdown chunk template matches MD-01; chunker tests updated.
- [ ] AC-10: `Chunk.metadata` includes lineage fields with sensible defaults for inline HTTP ingest.

### Upstream ingestion
- [ ] AC-11: Loader + parser + registry implemented; parser test with fixture files.
- [ ] AC-12: `ingest_from_dir.py` supports `--dry-run` and full embed path; documented in README.

### CLI tools
- [ ] AC-13: `preflight_embedding_pipeline.py`, `architecture_decision.py`, `inspect_fixtures.py` run as modules; exit codes as specified.

### Documentation & quality
- [ ] AC-14: `docs/technical/README.md` synced.
- [ ] AC-15: Architecture HTML + comparison ADR/note updated.
- [ ] AC-16: `conftest.py` `SAMPLE_CHUNK["chunk_id"]` uses `::`.
- [ ] AC-17: Full default suite green offline (`uv run pytest`); no new required API keys.
- [ ] AC-18: No imports from `app/services/semantic_cache/*` in `embedding_pipeline` or new scripts.

## Test Plan

- **Unit:** adapter, markdown chunker strings, parser valid/invalid JSON, loader file iteration, embedder client reuse (mock), tiktoken model selection, CLI `--dry-run` with mocked embedder.
- **Integration:** `test_milestone_e2e.py`; loader → parser → chunker chain; `ingest_from_dir` with tmp_path fixture dir.
- **Heavy (opt-in):** SMOKE-01/02; `preflight --live` optional.
- **Manual:**
  - `uv run pytest tests/embedding_pipeline/`
  - `uv run python -m app.scripts.preflight_embedding_pipeline`
  - `uv run python -m app.scripts.inspect_fixtures --dir tests/embedding_pipeline/fixtures/budget_files`
  - `uv run python -m app.scripts.ingest_from_dir --dir ... --dry-run`
  - Swagger POST with API-collection body
  - `uv run uvicorn app.main:app --reload` → `/docs`

## Verification

- Automated: `uv run pytest tests/embedding_pipeline/` and `uv run pytest` — record counts at implementation time.
- Heavy: `uv run pytest -m slow tests/embedding_pipeline/ --run-heavy` — optional.
- Manual: CLI invocations above — record exit codes.
- Not verified yet: spec only (pre-implementation).

## Documentation Plan

- `README.md`: verification recipe, new CLIs, markdown template note, ingest-from-dir.
- `docs/technical/README.md`: full embedding section (closes gap).
- `docs/arquitectura-estimador-cag.html`: upstream box + comparison table.
- ADR or feature-034 cross-link: master-ia vs estimator ingestion stages.
- `app/embedding_pipeline/SANITY_CHECK.md`: template change footnote.
- Second Brain: `learnings/docs/sesiones/sesion-07-embedding-pipeline-milestone-harness.md`.

## Reviewer checklist

- [ ] `uv run pytest tests/embedding_pipeline/` green offline.
- [ ] Milestone e2e test covers full HTTP path with real chunker.
- [ ] No orphan modules — loader/parser/adapters referenced from CLI or tests.
- [ ] `embedding_pipeline` still isolated from `semantic_cache`.
- [ ] Embedder: async, batch, retry, single client, cost stats.
- [ ] Chunk: markdown template, `::` ids, 7+ metadata keys, tiktoken aligned to settings.
- [ ] Dead router stub gone.
- [ ] README + `docs/technical/README.md` + architecture HTML aligned.
- [ ] Estimator comparison ADR/note explains what was adopted vs deferred.

## Estimation

- Size: **L** (was M — expanded scope)
- Estimated time: ~6–8 hours
- Planned steps: 12

## Implementation Plan

- [ ] Step 1: Fixture JSON + fix `conftest.py` `::`; add per-file budget fixtures under `fixtures/budget_files/`.
- [ ] Step 2: Hardening — remove router stub; single AsyncOpenAI client; settings-aware chunker + update `get_chunker`.
- [ ] Step 3: `PipelineDocument` schemas + adapter + refactor chunker to markdown template (update chunker tests).
- [ ] Step 4: Loader + parser + registry; unit tests; wire loader→parser→chunker test.
- [ ] Step 5: `test_milestone_e2e.py` (RED → GREEN) + slow smoke tests.
- [ ] Step 6: `ingest_from_dir.py` CLI with `--dry-run`.
- [ ] Step 7: `preflight_embedding_pipeline.py`, `architecture_decision.py`, `inspect_fixtures.py`.
- [ ] Step 8: API-collection embeddings request.
- [ ] Step 9: Update README, `docs/technical/README.md`, architecture HTML, ADR/note.
- [ ] Step 10: Full `uv run pytest`; optional heavy smoke; sync AC + verification in this doc.

## Learnings

- Estimator `ingestion/` is **upstream** (catalog → document extraction); master-ia `embedding_pipeline/` is **downstream** (chunk → embed). Adopt patterns only when wired end-to-end.
- Prefer component-level chunks (master-ia) over whole-budget documents (estimator) for retrieval granularity; borrow **markdown framing** from estimator, not their 1-doc-per-budget granularity.
- Do not ship PII/cleaning modules without orchestrator integration — estimator’s unwired layers are an anti-pattern.
- Keep stdlib logging; keep semantic_cache isolation; keep offline default test suite.
- Markdown template change alters embedding vectors — document and optionally re-run sanity pairs under `--run-heavy`.

## Open questions

- **Loader depth:** **resolved — non-recursive** (`*.json` in the given directory only; subdirectories ignored).
- **ADR placement:** **resolved — `docs/work-items/adr-001-embedding-pipeline-vs-estimator-ingestion.md`** (first ADR in repo).

## Architecture review (pre-implementation)

**Verdict:** approve with notes ([architecture-check-agent](fd8dc16d-283d-49f7-9128-627c7b724200), 2026-06-09).

- Extract shared ingest orchestration (`run_ingest` in `app/embedding_pipeline/ingest.py`) before `ingest_from_dir.py`; router and CLI delegate.
- Milestone e2e **complements** `test_router.py` (fixture file, zero-component budget, `::` ids, lineage metadata, markdown template) — does not duplicate router ACs.
- `inspect_fixtures.py` must use `FileSystemLoader` + parser registry — no ad-hoc JSON validation.
- Keep `architecture_decision.py` stdlib-only (no OpenAI/FastAPI imports).
- Hardening (step 2) before markdown template (step 3) to isolate test failures.

## Implementation progress

- [x] Step 1: Fixtures + conftest `::` fix + `fixtures/budget_files/`
- [x] Step 2: Hardening — remove router stub; single AsyncOpenAI; settings-aware chunker
- [x] Step 3: `PipelineDocument` + adapter + `run_ingest` + markdown chunker
- [x] Step 4: Loader + parser + registry + upstream chain test
- [ ] Step 5: `test_milestone_e2e.py` + slow smoke tests
- [ ] Step 6: `ingest_from_dir.py` CLI (`--dry-run`)
- [ ] Step 7: `preflight`, `architecture_decision`, `inspect_fixtures` CLIs
- [ ] Step 8: API-collection embeddings request
- [ ] Step 9: README, `docs/technical/README.md`, architecture HTML, ADR-001
- [ ] Step 10: Full `uv run pytest`; sync AC + verification

## Pull request

- [WIP] https://github.com/povedica/master-ia-lidr/pull/31 (label: `wip`)

## Deferred to Session 08+ (explicit, not in this feature)

- Vector DB persistence and similarity search over stored chunks.
- YAML data catalog with audit decisions and Postgres async jobs.
- PII pseudonymization and tabular Pandera cleaning.
- Shared low-level OpenAI embeddings client across semantic_cache and embedding_pipeline.
- HTTP endpoint accepting `source_name` from catalog instead of inline JSON.
