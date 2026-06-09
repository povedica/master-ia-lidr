# Feature (proposed v2): Embedding Pipeline Milestone Review, Hardening & Full Upstream Ingestion Parity

> **Draft proposal** — copy of the Phase 2 scope expansion (2026-06-09). Canonical active work item for Phase 1 closure remains [`feature-035-embedding-pipeline-milestone-review-harness.md`](feature-035-embedding-pipeline-milestone-review-harness.md).
>
> Consolidation work item for Session 07 (features **030–034**) plus full functional alignment with `ai-engineering/estimator/app/ingestion/` and `ai-engineering/estimator/data/`.
> Depends on: `feature-030` … `feature-034` (all merged).
> **Phase 1 (2026-06-08 — complete):** milestone harness, hardening, minimal upstream primitives, offline CLIs.
> **Phase 2 (2026-06-09 — pending):** close every functional gap vs the estimator ingestion subsystem — catalog, multi-format parsers, cleaning, PII, orchestrator, and catalog-driven HTTP/CLI paths — **wired end-to-end**, not copied verbatim.

## Objective

### Phase 1 (complete)

1. **Verify** the Session 07 milestone end to end (schemas → chunker → embedder → ingest → CLI).
2. **Harden** embedder client reuse, settings-aware tiktoken, dead stub removal.
3. **Introduce** minimal upstream path (filesystem → `Budget` → chunk → embed), `PipelineDocument`, markdown chunks.
4. **Ship** offline CLIs (preflight, simplified architecture decision, fixture inspect).
5. **Document** comparison baseline in ADR-001 and technical docs.

### Phase 2 (this update — implement next)

Bring **all estimator ingestion functionality** into `app/embedding_pipeline/` as a coherent upstream stage that feeds the existing downstream stage (chunk → embed), while preserving master-ia strengths:

| Keep (master-ia canonical) | Adopt from estimator (wired) |
|----------------------------|------------------------------|
| Component-level chunks (`1 chunk / component`) | YAML data catalog with `include \| review \| exclude` |
| `Budget` schema (Session 07 components model) | `LoadedBlob` loader with `data_root` + recursive walk |
| Async embedder + `IngestStats` cost in response | Multi-format parser registry (`json`, `txt`) |
| `run_ingest()` orchestration | `ParseContext` + catalog lineage/sensitivity propagation |
| stdlib logging (no structlog) | Transcript parser (tagged + legacy modes) |
| Isolation from `semantic_cache` | Cleaning + validation policy (repair / quarantine / discard) |
| | PII analysis + consistent pseudonymization before embed |
| | Full architecture-decision CLI (4 CAG constraints + 4 axes) |
| | Catalog inspect + catalog validate CLIs |
| | Catalog-driven ingest orchestrator shared by HTTP + CLI |

**Design principle (estimator lesson):** every module must appear in at least one orchestrated path. Estimator’s `cleaning/` and `pii/` are reference-only until wired — Phase 2 **must wire them** into `ingest_catalog_source()` before `run_ingest()`.

**Adaptation principle (not copy):** reimplement behaviors and contracts in master-ia naming and boundaries; map estimator’s commercial budget JSON (`phases`, `total_amount`) into master-ia’s `Budget` model via an explicit normalizer rather than changing the Session 07 schema.

## Context

### Session 07 baseline (master-ia)

- Milestone implemented and merged (PRs #25–#30). `uv run pytest tests/embedding_pipeline/` — 47 passing tests (2026-06-08).
- Flow today: inline `IngestRequest.budgets` → `JSONStructuralChunker.chunk()` → `OpenAIEmbedder.embed_many()` → `IngestResponse`.
- Strengths to **keep**: component-level chunking (finer than estimator’s 1-doc-per-budget), async embedder with batching/retry/cost stats, 47 offline tests, explicit isolation from `app/services/semantic_cache/*`.

### Estimator comparison — Phase 1 snapshot (2026-06-08)

Reference repo: `/Users/pablo.poveda/CodeProjects/ai-engineering/estimator/app/ingestion/` + `/Users/pablo.poveda/CodeProjects/ai-engineering/estimator/data/`.

| Dimension | master-ia after Phase 1 | estimator `ingestion/` | Phase 2 action |
|-----------|-------------------------|------------------------|----------------|
| Upstream ingest | `ingest_from_dir` → `Budget[]` | Catalog → loader → parser → `Document[]` | Full catalog orchestrator |
| Intermediate contract | `PipelineDocument` (partial metadata) | `Document` + `DocumentMetadata` | Align metadata fields; propagate PII flags |
| Chunk granularity | 1 chunk / component | 1 document / budget file (JSON) or turn/block (TXT) | **Keep** component chunks for JSON; 1 chunk / transcript document |
| Chunk text | Markdown per component | Markdown per whole budget (commercial schema) | Keep component template; add commercial normalizer |
| Embedding | Full async pipeline + cost stats | Not in ingestion | **Keep** master-ia embedder |
| Data catalog | None | `data/catalog/catalog.yaml` with audit scores | Port catalog models + loader + inspect |
| Loader | Non-recursive `*.json` paths | `LoadedBlob` + `data_root` + `rglob` + format filter | Upgrade loader; keep backward-compatible API |
| Parsers | `budget_json` → `Budget` only | `budget_json` + `transcript_txt` → `Document` | Add transcript parser; dual JSON paths |
| Cleaning | None | pandas repair + Pandera validate + quarantine/discard | Wire on raw records before document render |
| PII | Field reserved only | Presidio ES + custom recognizers + pseudonymizer | Wire before embed; in-memory store (no Postgres) |
| Jobs async + DB | Sync HTTP 200 | Postgres `ingestion_jobs` + 202/poll | In-memory job store + optional async pattern (no Postgres) |
| HTTP ingest | `POST /embeddings/ingest` inline JSON | `POST /ingestion/runs` by `source_name` | Add catalog-driven route; keep inline route |
| Ops CLIs | preflight, simplified architecture, inspect_fixtures | architecture, catalog inspect, catalog loader | Expand CLIs to estimator parity |
| Logging | stdlib | structlog | **Keep** stdlib |

### Full functional gap analysis (2026-06-09)

Detailed module-by-module comparison after Phase 1 implementation.

#### A. Data layer (`estimator/data/`)

| Estimator asset | Purpose | master-ia today | Phase 2 |
|-----------------|---------|-----------------|---------|
| `data/catalog/catalog.yaml` | Audited source registry with `include/review/exclude`, quality 1–5, sensitivity, lineage | Missing | Add `data/catalog/catalog.yaml` (or `tests/.../fixtures/catalog.yaml` for tests) mirroring estimator structure; sources point at `data/seed/` layout |
| `data/seed/budgets/*.json` | Commercial budget JSON (`client_name`, `phases`, `total_amount`, PII) | Different schema in `fixtures/budget_files/` (`client_metadata`, `components`) | Add `data/seed/budgets/` with estimator-compatible samples + normalizer to `Budget` |
| `data/seed/transcripts/*.txt` | Tagged + legacy transcript formats | Missing | Add transcript fixtures; wire `TranscriptTxtParser` |

#### B. Catalog subsystem (`catalog/`)

| Estimator module | Behavior | master-ia today | Phase 2 |
|------------------|----------|-----------------|---------|
| `catalog/models.py` | `DataCatalog`, `CatalogSource`, `QualityScore`, `Sensitivity`, `CatalogDecision` enum, validators (snake_case name, reason required when not `include`) | Missing | Implement under `app/embedding_pipeline/catalog/` |
| `catalog/loader.py` | `load_catalog(path)` + validate CLI | Missing | Implement + `python -m app.scripts.load_catalog` |
| `catalog/inspect.py` | Facts-only folder inspection (`file_count`, `total_size_mb`, `latest_modified`, `formats_detected`) per child folder | `inspect_fixtures.py` only validates budget JSON | Extend inspect CLI with `inspect_data_root` facts table; keep budget validation as sub-command |

#### C. Loader (`loaders/filesystem.py`)

| Behavior | Estimator | master-ia Phase 1 | Phase 2 |
|----------|-----------|-------------------|---------|
| `LoadedBlob(relative_path, bytes_)` | Yes | No (yields `Path`) | Add dataclass; parsers consume bytes |
| `data_root` resolution | `INGESTION_DATA_ROOT` + `CatalogSource.location` | Single `--dir` argument | Settings: `embedding_pipeline_data_root` (document in `.env.example`) |
| Recursive walk | `rglob("*")` when location is directory | Non-recursive `iterdir()` | `iter_blobs(location, formats)`; retain `iter_budget_files()` as thin wrapper for backward compat |
| Format filter | Extension ∈ `formats` set | `.json` only | Filter by catalog `source.format` |
| Missing location | `FileNotFoundError` with path | `FileNotFoundError` on missing dir | Same hard-fail semantics |

#### D. Parsers (`parsers/`)

| Parser | Estimator output | master-ia today | Phase 2 |
|--------|------------------|-----------------|---------|
| `budget_json` | 1 `Document` / file; markdown from commercial fields (`## Cliente`, `## Fases`); `extra` with `budget_id`, `client_code`, `currency` | `parse_budget_file` → `Budget` (components schema) | **Two paths:** (1) existing components JSON → `Budget`; (2) commercial JSON → `normalize_commercial_budget()` → `Budget` then existing adapter. Document-level commercial markdown available for inspect-only if needed |
| `transcript_txt` | 1 `Document` / turn (tagged) or / paragraph block (legacy); `extra.speaker`, `extra.timestamp`, `extra.format_mode` | Missing | Implement; output `PipelineDocument` directly (no `Budget` step) |
| `protocol.py` | `ParseContext(source, source_version, ingested_at)` | Minimal `BudgetParser` callable | Full `Parser` Protocol + `ParseContext` with `CatalogSource` |
| `registry.py` | `ParserRegistry` with `default_registry()` | Dict map `"json"` → callable | Class registry; register JSON + TXT parsers |

**Schema divergence (critical):**

```text
estimator commercial JSON          master-ia Session 07 JSON
─────────────────────────          ─────────────────────────
budget_id                            budget_id
client_name, client_code             client_metadata {name, sector, country}
currency, total_amount, signed_at    year, total_estimated_hours
phases[{name, weeks, amount}]        components[{component_id, name, description, ...}]
contact, contact_email, notes        project_summary, main_technology
```

**Normalization rule (Phase 2):** `normalize_commercial_budget(dict) -> Budget` maps each `phase` to a synthetic `BudgetComponent` (`component_id=PHASE-{idx}`, `estimated_hours=weeks*40` heuristic or `amount`-derived placeholder documented in code), copies `client_name` → `client_metadata.name`, infers `sector` from `notes` or `"unknown"`, sets `main_technology` from notes or `"unspecified"`. Tests must use estimator seed files as golden inputs.

#### E. Documents / intermediate contract

| Field | Estimator `DocumentMetadata` | master-ia `PipelineDocumentMetadata` | Phase 2 |
|-------|------------------------------|----------------------------------------|---------|
| `source_name` | ✓ | ✓ | Keep |
| `source_version` | ✓ (catalog version) | ✓ | Keep |
| `ingested_at` | `datetime` UTC | `str` ISO-8601 | Accept both in tests; prefer `datetime` internally, serialize to str at chunk boundary if needed |
| `lineage` | ✓ from catalog source | ✓ | Populate from catalog on catalog-driven runs |
| `sensitivity_pii_flags` | ✓ from catalog | Missing | Add field; copy from `CatalogSource.sensitivity.pii_flags` |
| `sensitivity_access_level` | ✓ | ✓ (as `sensitivity_access_level`) | Rename for parity: `sensitivity_access_level` OK |
| `location` | blob relative path | ✓ | Keep |
| `extra` | format-specific | ✓ | Populate per parser |

#### F. Cleaning (`cleaning/` — estimator reference, unwired)

| Module | Behavior | Phase 2 requirement |
|--------|----------|---------------------|
| `cleaning/budget_records.py` | pandas: null placeholders → NA, currency upper, date coerce, numeric coerce, hash dedup keeping latest `signed_at` | Implement for **commercial** records before normalization; skip or no-op for already-validated `Budget` components JSON |
| `cleaning/schemas.py` | Pandera `BudgetRecord` schema (`budget_id` pattern, currency isin, amount range) | Port schema; adapt IDs to accept both `BUDGET-YYYY-NNNN` and `BUD-YYYY-NNN` OR normalize IDs during cleaning |
| `cleaning/policy.py` | `validate_with_policy` → `valid | quarantined | discarded` + JSON report | Wire in orchestrator; quarantined/discarded logged and excluded from embed; report attached to job result |

**Dependencies:** `pandas`, `pandera` — add via `uv add pandas pandera`; heavy tests mock DataFrames where possible.

#### G. PII (`pii/` — estimator reference, unwired)

| Module | Behavior | Phase 2 requirement |
|--------|----------|---------------------|
| `pii/analyzer.py` | Presidio `AnalyzerEngine` with Spanish spaCy + custom recognizers | Implement; gate behind `embedding_pipeline_pii_enabled` setting (default `false` in tests) |
| `pii/recognizers.py` | `BUDGET_ID`, `CLIENT_CODE` pattern recognizers | Port |
| `pii/pseudonymizer.py` | HMAC-SHA256 + consistent pseudonym via mapping store | Port; use `InMemoryMappingStore` (no Postgres) |
| `pii/mapping_store.py` | Protocol + in-memory + Postgres impl | Ship in-memory only; Postgres deferred to Session 08 |

**Dependencies:** `presidio-analyzer`, `spacy`, Spanish model — opt-in heavy tests `@pytest.mark.slow`; default suite uses stub analyzer.

**Orchestration hook:** when `catalog_source.sensitivity.has_pii` or global flag enabled, run `pseudonymize(document.text)` on each `PipelineDocument` before chunking; record `applied` mappings count in job report (not in embed response).

#### H. Orchestrator

| Estimator `ingest_source()` | Phase 2 `ingest_catalog_source()` |
|-----------------------------|-------------------------------------|
| Validates catalog decision == `include` | Same; raise `IngestionRejected` → HTTP 400 |
| Updates `jobs_repo` pending → running → completed/failed | Update `InMemoryJobsRepository` (new module) |
| `loader.iter_blobs` → `parser.parse` → append `Document` | Same; then branch: JSON budgets → normalize → `Budget[]` → existing chunker; TXT → `PipelineDocument[]` → map 1:1 to `Chunk` without component adapter |
| Sync inside BackgroundTask | Async-friendly: run CPU-bound parse/clean in `asyncio.to_thread`; embed stays async |
| Returns `list[Document]` | Returns `IngestRunResult(documents, budgets, chunks, stats, validation_report, pii_applied_count)` |

**Unified end-to-end orchestration:**

```text
catalog + source_name
  → ingest_catalog_source()     # upstream (estimator parity)
  → [optional] clean + validate
  → [optional] pseudonymize
  → budgets_to_chunks()         # existing chunker path
  → transcript_docs_to_chunks() # new 1:1 path
  → run_ingest() / embedder     # downstream (unchanged)
```

#### I. HTTP API

| Estimator | Phase 2 master-ia |
|-----------|-------------------|
| `POST /api/v1/ingestion/runs` `{source_name}` → 202 + `job_id` | `POST /api/v1/embeddings/ingest/catalog` `{source_name}` → 202 + `job_id` (new router or extend `embeddings.py`) |
| `GET /api/v1/ingestion/jobs/{job_id}` | `GET /api/v1/embeddings/ingest/jobs/{job_id}` |
| BackgroundTask + Postgres session | `BackgroundTasks` + in-memory job store (request lifecycle safe) |
| Existing inline ingest | **Keep** `POST /api/v1/embeddings/ingest` unchanged |

Job view fields: `job_id`, `source_name`, `status`, `documents_count`, `chunks_count`, `error_message`, `validation_report`, `started_at`, `finished_at`.

#### J. CLI tools

| Estimator CLI | master-ia Phase 1 | Phase 2 target |
|---------------|-------------------|----------------|
| `python -m app.ingestion.architecture` | Simplified `architecture_decision.py` (2 args) | Port full `CAGViability`, `CorpusProfile`, `ModelProfile`, `assess_cag_viability`, `recommend_architecture`, Proyecto 2 defaults |
| `python -m app.ingestion.catalog.inspect` | `inspect_fixtures.py` (budget counts only) | `inspect_data_catalog.py` with folder facts; subcommand for budget validation |
| `python -m app.ingestion.catalog.loader` | Missing | `load_catalog.py` validate + print included sources |
| N/A | `ingest_from_dir.py` | Extend: `--catalog path --source presupuestos_json` OR keep `--dir` for dev |
| N/A | `preflight_embedding_pipeline.py` | Add checks: catalog loads, data_root exists, optional PII deps |

#### K. Architecture decision CLI (estimator detail)

Estimator `architecture.py` implements:

- **4 CAG constraints (AND):** `context_window_ok`, `cost_ok` (prefix caching + refresh ≥ 7 days), `latency_ok`, `lost_in_the_middle_ok` (both vs 100k token budget).
- **4 decision axes:** volume, refresh frequency, traceability required, access control required → `CAG | Hybrid | RAG`.
- **Defaults:** Proyecto 2 corpus (250k tokens, weekly refresh, traceability + access control) → expect `RAG`.

Phase 2 replaces simplified `recommend(corpus_tokens, refresh_days)` with full dataclasses; CLI flags: `--corpus-tokens`, `--refresh-days`, `--traceability`, `--access-control`, `--model-context-window`.

#### L. What master-ia has that estimator lacks (keep)

- `OpenAIEmbedder` with batching, retry, `IngestStats` cost exposure.
- Component-level retrieval granularity for budget JSON.
- `compare.py` cosine sanity CLI.
- `SANITY_CHECK.md` semantic pair validation.
- Full offline fast test suite without DB.

### Phase 1 gaps (resolved)

- ~~Milestone e2e harness~~ ✓
- ~~`docs/technical/README.md` embedding section~~ ✓
- ~~`conftest.py` `::` chunk ids~~ ✓
- ~~Dead `router.py` stub~~ ✓
- ~~Per-batch `AsyncOpenAI` client~~ ✓
- ~~Hardcoded tiktoken model~~ ✓

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

### Excludes (both phases)
- Vector DB persistence, embedding storage, retrieval API (Session 08).
- Postgres-backed `ingestion_jobs` and `pii_mappings` tables (use in-memory implementations in Phase 2).
- `structlog` migration.
- Merging `OpenAIEmbedder` with `semantic_cache/openai_embeddings.py`.
- numpy / scikit-learn.
- Breaking HTTP contract: `POST /api/v1/embeddings/ingest` body shape stays `IngestRequest`.

### Phase 2 includes (estimator parity — implement)

#### H. Data catalog
- `app/embedding_pipeline/catalog/models.py`, `loader.py` — Pydantic models mirroring estimator `DataCatalog` / `CatalogSource` / `QualityScore` / `Sensitivity` / `CatalogDecision`.
- `data/catalog/catalog.yaml` + `data/seed/budgets/` + `data/seed/transcripts/` committed as learning corpus (estimator-compatible samples).
- Settings: `embedding_pipeline_data_root` (default `data/seed`), `embedding_pipeline_catalog_path` (default `data/catalog/catalog.yaml`).

#### I. Loader upgrade
- `LoadedBlob` dataclass; `FileSystemLoader(data_root).iter_blobs(location, formats)`.
- Backward-compatible `iter_budget_files(directory)` delegating to `iter_blobs`.

#### J. Parser expansion
- `ParseContext` + `Parser` Protocol returning `Iterable[PipelineDocument]`.
- `CommercialBudgetJsonParser` + `ComponentsBudgetJsonParser` (or single parser with schema detection).
- `TranscriptTxtParser` with tagged vs legacy heuristic (`≥3` tagged lines).
- `normalize_commercial_budget()` in `app/embedding_pipeline/normalizers/commercial_budget.py`.
- `ParserRegistry` class with `default_registry()`.

#### K. Cleaning (wired)
- `app/embedding_pipeline/cleaning/` — `budget_records.py`, `schemas.py`, `policy.py` adapted from estimator.
- Orchestrator calls `clean_budget_records` → `validate_with_policy` for commercial JSON path only.
- Quarantined/discarded rows logged with structured keys; never embedded.

#### L. PII (wired, opt-in)
- `app/embedding_pipeline/pii/` — analyzer, recognizers, pseudonymizer, `InMemoryMappingStore`.
- Settings: `embedding_pipeline_pii_enabled` (bool, default `false`), `embedding_pipeline_pseudonymization_salt` (required when PII enabled), `presidio_spacy_model` (default `es_core_news_md`).
- Orchestrator applies pseudonymization when source `sensitivity.has_pii` and setting enabled.

#### M. Orchestrator + jobs
- `app/embedding_pipeline/orchestrator.py` — `ingest_catalog_source()`, `IngestionRejected`.
- `app/embedding_pipeline/jobs.py` — `InMemoryJobsRepository`, `IngestionJob` dataclass.
- `app/embedding_pipeline/ingest.py` — extend with `run_catalog_ingest(source_name, ...)` composing upstream + `run_ingest()`.
- `transcript_docs_to_chunks()` for non-budget documents (1 document → 1 chunk, `chunk_id=document.id`).

#### N. HTTP routes
- `POST /api/v1/embeddings/ingest/catalog` → 202 + `job_id`.
- `GET /api/v1/embeddings/ingest/jobs/{job_id}` → job status view.
- Background task runs orchestrator; poll endpoint for completion.

#### O. CLI expansion
- Replace simplified `architecture_decision.py` with full estimator logic.
- Add `load_catalog.py`; extend `inspect_fixtures.py` → `inspect_data_root.py` (or unified `inspect_corpus.py` with subcommands `facts` | `budgets`).
- Extend `ingest_from_dir.py` with `--catalog` + `--source` flags.
- API-collection entries for catalog ingest + job poll.

#### P. Tests & fixtures
- Port estimator invalid/valid patterns into `tests/embedding_pipeline/fixtures/`.
- `test_catalog.py`, `test_commercial_normalizer.py`, `test_transcript_parser.py`, `test_cleaning_policy.py`, `test_pii_pseudonymizer.py` (PII tests use stub unless `--run-heavy`).
- `test_catalog_ingest_e2e.py` — offline with fake embedder, real parsers, in-memory jobs.
- Golden files from `estimator/data/seed/` referenced in tests.

#### Q. Documentation
- Update ADR-001: Phase 2 supersedes deferred items (catalog, PII, cleaning now in scope).
- Update `docs/technical/README.md`, README, architecture HTML with two-stage diagram including cleaning + PII boxes.
- `.env.example` entries for new settings (no secrets).

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

### G. Documentation (Phase 1)

- DOCG-01: `docs/technical/README.md` updated (module, route, env vars, scripts).
- DOCG-02: Architecture HTML and ADR/comparison note published.

### H. Data catalog (Phase 2)

- CAT-01: `load_catalog(path)` validates YAML into `DataCatalog`; duplicate source names rejected.
- CAT-02: `CatalogSource` with `decision=review|exclude` requires non-empty `decision_reason`.
- CAT-03: `DataCatalog.find(name)` and `included_sources()` behave as estimator.
- CAT-04: Committed `data/catalog/catalog.yaml` lists at least `presupuestos_json` (include), `transcripciones_txt` (review), `rate_card_xlsx` (exclude) matching estimator semantics.

### I. Loader upgrade (Phase 2)

- LOAD-01: `LoadedBlob` carries `relative_path` and `bytes_`.
- LOAD-02: `iter_blobs("budgets", {"json"})` walks `data_root/budgets` recursively.
- LOAD-03: Missing catalog location raises `FileNotFoundError` with resolved absolute path in message.
- LOAD-04: `iter_budget_files` still works for existing tests and `ingest_from_dir --dir`.

### J. Parsers & normalization (Phase 2)

- PARSE-01: Components JSON (Session 07 schema) still parses to `Budget` via existing validation.
- PARSE-02: Commercial JSON (`estimator/data/seed/budgets/BUDGET-2024-0001.json`) normalizes to `Budget` with ≥1 component per phase.
- PARSE-03: `TranscriptTxtParser` on tagged fixture yields one document per speaker turn with `extra.speaker` and `extra.timestamp`.
- PARSE-04: Legacy transcript (`transcripcion_2023-09-08_legacy.txt`) yields paragraph-block documents with `extra.format_mode=legacy`.
- PARSE-05: Parser registry returns correct parser for `json` and `txt`; unknown format raises `KeyError`.
- PARSE-06: `ParseContext.ingested_at` is constant across all blobs in one orchestrator run.

### K. Metadata alignment (Phase 2)

- META-01: `PipelineDocumentMetadata` gains `sensitivity_pii_flags: list[str]`.
- META-02: Catalog-driven runs populate `lineage` and `sensitivity_*` from `CatalogSource`.
- META-03: `Chunk.metadata` includes `sensitivity_pii_flags` when present.

### L. Cleaning policy (Phase 2)

- CLEAN-01: `clean_budget_records` normalizes `TBD`/`N/A`/empty to NA, uppercases currency, coerces dates and amounts.
- CLEAN-02: Duplicate `budget_id` rows keep latest `signed_at`.
- CLEAN-03: `validate_with_policy` routes invalid rows to quarantine or discard per estimator check families.
- CLEAN-04: Orchestrator embeds only `valid` rows; `validation_report` summary on job record.

### M. PII (Phase 2)

- PII-01: `BudgetIdRecognizer` and `ClientCodeRecognizer` detect `BUDGET-YYYY-NNNN` and `CLI-NNNN` in Spanish text.
- PII-02: `ConsistentPseudonymizer` returns same pseudonym for same input hash across calls (`InMemoryMappingStore`).
- PII-03: When `embedding_pipeline_pii_enabled=true`, orchestrator pseudonymizes document text before chunking; Spanish name in transcript replaced consistently.
- PII-04: Default test suite uses stub analyzer (no spaCy download); heavy tests opt-in.

### N. Orchestrator & jobs (Phase 2)

- ORCH-01: `ingest_catalog_source` rejects unknown source → `IngestionRejected`.
- ORCH-02: Rejects `review` and `exclude` sources with reason in exception message.
- ORCH-03: Job transitions: `pending` → `running` → `completed`|`failed`.
- ORCH-04: `run_catalog_ingest` produces `IngestResponse`-compatible result with correct `stats` after embed.
- ORCH-05: Transcript source ingests without `Budget` normalization (direct `PipelineDocument` → `Chunk`).

### O. HTTP catalog ingest (Phase 2)

- HTTP-01: `POST /api/v1/embeddings/ingest/catalog` with valid included `source_name` returns `202` and `job_id`.
- HTTP-02: Unknown source → `404`; non-include decision → `400` with `decision` and `decision_reason`.
- HTTP-03: `GET .../jobs/{job_id}` returns status and counts; unknown job → `404`.
- HTTP-04: Inline `POST /embeddings/ingest` unchanged and tests still pass.

### P. CLI parity (Phase 2)

- CLI-04: `architecture_decision.py` prints failing CAG constraints and `CAG|Hybrid|RAG` with Proyecto 2 defaults when run with no args.
- CLI-05: `load_catalog.py` validates catalog file exit 0/1.
- CLI-06: `inspect` subcommand `facts` prints per-folder table matching estimator inspect layout.
- CLI-07: `ingest_from_dir --catalog X --source presupuestos_json` runs full path (dry-run supported).

## Technical Approach

### Module layout — Phase 1 (shipped)

```text
app/embedding_pipeline/
├── schemas.py, adapters.py, chunker.py, embedder.py, ingest.py
├── loaders/filesystem.py
├── parsers/{protocol,registry,budget_json}.py
└── SANITY_CHECK.md
```

### Module layout — Phase 2 (target)

```text
data/
├── catalog/catalog.yaml
└── seed/{budgets/*.json, transcripts/*.txt}

app/embedding_pipeline/
├── schemas.py                    # + sensitivity_pii_flags, job models
├── catalog/
│   ├── models.py
│   └── loader.py
├── loaders/filesystem.py         # LoadedBlob + iter_blobs
├── parsers/
│   ├── protocol.py               # ParseContext + Parser Protocol
│   ├── registry.py               # ParserRegistry
│   ├── budget_json.py            # components path (existing)
│   ├── commercial_budget_json.py # commercial → PipelineDocument or raw dict
│   └── transcript_txt.py
├── normalizers/
│   └── commercial_budget.py      # commercial dict → Budget
├── cleaning/
│   ├── budget_records.py
│   ├── schemas.py
│   └── policy.py
├── pii/
│   ├── analyzer.py
│   ├── recognizers.py
│   ├── pseudonymizer.py
│   └── mapping_store.py          # InMemory only
├── orchestrator.py
├── jobs.py                       # InMemoryJobsRepository
├── ingest.py                     # run_ingest + run_catalog_ingest
├── adapters.py, chunker.py, embedder.py
└── SANITY_CHECK.md

app/routers/embeddings.py         # + catalog ingest routes
app/scripts/
├── compare.py
├── ingest_from_dir.py            # + --catalog --source
├── preflight_embedding_pipeline.py
├── architecture_decision.py    # full estimator logic
├── load_catalog.py
└── inspect_corpus.py             # facts + budget validation subcommands
```

### Orchestration paths (everything wired)

| Path | Flow |
|------|------|
| HTTP inline ingest (Phase 1) | `IngestRequest` → chunker → embedder → `200` |
| HTTP catalog ingest (Phase 2) | `source_name` → orchestrator → clean → PII → chunk → embed → job `completed` |
| ingest_from_dir `--dir` | loader → parser → `Budget[]` → chunker → embedder |
| ingest_from_dir `--catalog` | catalog → orchestrator → same downstream |
| Milestone e2e | fixture JSON → HTTP inline → fake embedder |
| Catalog e2e (Phase 2) | seed data → catalog source → fake embedder → job poll |
| Upstream unit tests | per-module with estimator golden files |

### Dependency injection

- Update `get_chunker` signature to `get_chunker(settings: Annotated[Settings, Depends(get_settings)]) -> JSONStructuralChunker`.
- Tests override settings via existing patterns or env in `conftest.py`.

### Estimator patterns adapted (not copied verbatim)

| Estimator pattern | master-ia Phase 2 adaptation |
|-------------------|------------------------------|
| Postgres `ingestion_jobs` | `InMemoryJobsRepository` with same status enum; Session 08 swaps implementation |
| Postgres `MappingsRepository` for PII | `InMemoryMappingStore` only |
| `structlog` | stdlib `logging` + stable `extra` keys |
| 1 `Document` per budget JSON file | Normalize to `Budget`, then **component-level** chunks (master-ia retrieval granularity) |
| Commercial markdown (`## Cliente`, `## Fases`) | Keep component markdown template; commercial fields mapped into components |
| `ingest_source` sync in BackgroundTask | CPU-bound steps in `asyncio.to_thread`; embed step async |
| `@lru_cache` catalog at startup | `load_catalog` per request or explicit `get_catalog()` dependency with optional mtime reload |
| XLSX / DOCX / PDF parsers | Out of scope until sources exist in catalog |

### Real APIs (do not invent)

- `JSONStructuralChunker.chunk`, `OpenAIEmbedder.embed_many` / `embed_one`, `IngestRequest` / `IngestResponse`, `compare.cosine_similarity`, FastAPI `dependency_overrides`.

## Acceptance Criteria

### Milestone harness
- [x] AC-01: `sample_budgets.json` + conftest fixture exist; ≥2 budgets, ≥3 components.
- [x] AC-02: `test_milestone_e2e.py` passes E2E-01..E2E-08 offline.
- [x] AC-03: `@pytest.mark.slow` smoke tests exist and are deselected by default.
- [x] AC-04: API-collection `embeddings/Ingest Budgets.yml` + `folder.yml` exist.

### Hardening
- [x] AC-05: Dead `router.py` stub removed; package imports cleanly.
- [x] AC-06: Single `AsyncOpenAI` client per embedder instance; embedder tests green.
- [x] AC-07: Chunker encoder driven by `embedding_pipeline_model`; chunker + router tests green.

### Contracts & chunk text
- [x] AC-08: `PipelineDocument` / `PipelineDocumentMetadata` defined and used by adapter.
- [x] AC-09: Markdown chunk template matches MD-01; chunker tests updated.
- [x] AC-10: `Chunk.metadata` includes lineage fields with sensible defaults for inline HTTP ingest.

### Upstream ingestion
- [x] AC-11: Loader + parser + registry implemented; parser test with fixture files.
- [x] AC-12: `ingest_from_dir.py` supports `--dry-run` and full embed path; documented in README.

### CLI tools
- [x] AC-13: `preflight_embedding_pipeline.py`, `architecture_decision.py`, `inspect_fixtures.py` run as modules; exit codes as specified.

### Documentation & quality (Phase 1)
- [x] AC-14: `docs/technical/README.md` synced.
- [x] AC-15: Architecture HTML + comparison ADR/note updated.
- [x] AC-16: `conftest.py` `SAMPLE_CHUNK["chunk_id"]` uses `::`.
- [x] AC-17: Full default suite green offline (`uv run pytest`); no new required API keys.
- [x] AC-18: No imports from `app/services/semantic_cache/*` in `embedding_pipeline` or new scripts.

### Phase 2 — catalog & data
- [ ] AC-19: `data/catalog/catalog.yaml` + seed corpus committed; `load_catalog` validates.
- [ ] AC-20: Settings `embedding_pipeline_data_root` and `embedding_pipeline_catalog_path` documented in `.env.example`.

### Phase 2 — loader & parsers
- [ ] AC-21: `iter_blobs` recursive walk + format filter; `LoadedBlob` used by parsers.
- [ ] AC-22: Commercial + components JSON paths both produce embeddable chunks in tests.
- [ ] AC-23: Transcript tagged + legacy fixtures parse to expected document counts.

### Phase 2 — cleaning & PII (wired)
- [ ] AC-24: Quarantined/discarded commercial rows never reach embedder (unit + integration test).
- [ ] AC-25: PII pseudonymization opt-in; stub path default; heavy test proves Spanish PERSON redaction.

### Phase 2 — orchestrator & HTTP
- [ ] AC-26: `ingest_catalog_source` enforces catalog decisions; job lifecycle in memory.
- [ ] AC-27: Catalog HTTP routes `202`/`GET` work with TestClient + fake embedder.
- [ ] AC-28: Inline ingest route regression tests still pass.

### Phase 2 — CLI & docs
- [ ] AC-29: Full `architecture_decision` CLI matches estimator Proyecto 2 output (`RAG`).
- [ ] AC-30: ADR-001 updated; architecture HTML shows cleaning + PII + catalog boxes.
- [ ] AC-31: Default `uv run pytest` green without spaCy/Presidio installed (stubs/mocks).

## Test Plan

### Phase 1 (complete)
- Unit: adapter, chunker, parser, loader, embedder, CLIs.
- Integration: `test_milestone_e2e.py`, upstream chain, `ingest_from_dir`.
- Heavy: SMOKE-01/02, `preflight --live`.

### Phase 2 (add)
- **Unit:**
  - Catalog model validators (duplicate name, decision_reason).
  - `normalize_commercial_budget` golden tests against `data/seed/budgets/BUDGET-2024-0001.json`.
  - Transcript parser: tagged fixture ≥5 turns; legacy ≥2 blocks.
  - Cleaning: null placeholders, dedup by `signed_at`, quarantine vs discard routing.
  - PII: recognizer regex tests; pseudonymizer consistency with `InMemoryMappingStore`.
  - Architecture CLI: Proyecto 2 defaults → `RAG`, failing constraints list non-empty.
- **Integration:**
  - `test_catalog_ingest_e2e.py`: `presupuestos_json` → chunks == total components across seed budgets.
  - Review source `transcripciones_txt` rejected with 400 when invoked via HTTP.
  - Job poll returns `completed` with `documents_count` and `chunks_count`.
- **Heavy (opt-in):** Presidio analyzer on transcript with real spaCy model.
- **Manual:**
  - `uv run python -m app.scripts.load_catalog data/catalog/catalog.yaml`
  - `uv run python -m app.scripts.inspect_corpus facts data/seed`
  - `uv run python -m app.scripts.architecture_decision` (no args → Proyecto 2)
  - `uv run python -m app.scripts.ingest_from_dir --catalog data/catalog/catalog.yaml --source presupuestos_json --dry-run`
  - Swagger: catalog ingest + job poll

## Verification

### Phase 1
- **Verified (2026-06-09):** `uv run pytest tests/embedding_pipeline/` — 83 passed, 2 slow deselected.
- **Verified (2026-06-09):** `uv run pytest` — 455 passed, 11 skipped, 12 deselected (default suite).
- **Not verified:** `uv run pytest -m slow tests/embedding_pipeline/ --run-heavy` (requires live `OPENAI_API_KEY`).
- **Residual risk:** markdown template invalidates prior `SANITY_CHECK.md` vectors; re-measure under `--run-heavy` when needed.

### Phase 2 (pending)
- **Not started:** AC-19..AC-31.
- **Target:** default suite green without spaCy; PII heavy tests opt-in.
- **Residual risk:** pandas/pandera add cold-start import cost; commercial normalizer heuristic may produce weak component boundaries for retrieval evals.

## Documentation Plan

### Phase 1 (done)
- README, `docs/technical/README.md`, architecture HTML, ADR-001, SANITY_CHECK footnote, Second Brain session note.

### Phase 2 (pending)
- `README.md`: catalog ingest, job poll, PII opt-in, `data/seed` layout, commercial vs components JSON.
- `docs/technical/README.md`: two-stage pipeline with cleaning + PII boxes.
- `docs/arquitectura-estimador-cag.html`: catalog, orchestrator, job routes.
- ADR-001 revision: Phase 2 supersedes prior deferrals for catalog/cleaning/PII.
- Second Brain: schema normalization + estimator parity session note.

## Reviewer checklist

### Phase 1 (complete)
- [x] `uv run pytest tests/embedding_pipeline/` green offline.
- [x] Milestone e2e test covers full HTTP path with real chunker.
- [x] No orphan modules — loader/parser/adapters referenced from CLI or tests.
- [x] `embedding_pipeline` still isolated from `semantic_cache`.
- [x] Embedder: async, batch, retry, single client, cost stats.
- [x] Chunk: markdown template, `::` ids, 7+ metadata keys, tiktoken aligned to settings.
- [x] Dead router stub gone.
- [x] README + `docs/technical/README.md` + architecture HTML aligned.
- [x] Estimator comparison ADR explains Phase 1 adoption.

### Phase 2 (pending)
- [ ] Catalog YAML loads; seed corpus matches estimator layout.
- [ ] Commercial JSON normalizes; transcript parser handles tagged + legacy.
- [ ] Cleaning + PII wired in orchestrator (not orphan modules).
- [ ] Catalog HTTP 202/poll works with in-memory jobs.
- [ ] Inline ingest regression green.
- [ ] Default pytest green without spaCy; PII heavy opt-in.
- [ ] ADR-001 + architecture HTML updated for Phase 2.

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
| *(prior)* | docs(feature-035) | Canonical work item |
| *(prior)* | test(embedding-pipeline) | Milestone fixtures + conftest `::` fix |
| *(prior)* | refactor(embedding-pipeline) | Harden embedder client + settings-aware chunker |
| *(prior)* | feat(embedding-pipeline) | PipelineDocument adapter + markdown chunks + run_ingest |
| *(prior)* | feat(embedding-pipeline) | Filesystem loader + budget JSON parser |
| *(prior)* | test(embedding-pipeline) | Milestone e2e harness + slow smoke tests |
| *(prior)* | feat(embedding-pipeline) | ingest CLI + ops scripts + API collection |
| *(prior)* | docs(feature-035) | README, technical docs, ADR-001, architecture HTML sync |
| `24e8fb8` | `test(embedding-pipeline): add ten diverse budget file fixtures` | Ten valid per-file budgets across sectors for manual CLI exercises. |
| `1c0d884` | `test(embedding-pipeline): add invalid budget fixtures for parser checks` | Five invalid JSON samples under `budget_files/invalids/`. |
| `671fd0d` | `test(embedding-pipeline): update corpus counts after budget_files expansion` | Tests expect 13 files and 24 components in `budget_files/`. |
| `9282df2` | `docs(feature-035): log fixture corpus commits in work item` | Repository commits table updated with fixture expansion hashes. |

## Estimation

- Phase 1 size: **L** — ~6–8 hours (complete).
- Phase 2 size: **XL** — ~12–16 hours (catalog + parsers + cleaning + PII + HTTP jobs + docs).
- Phase 2 planned steps: 14 baby steps (below).

## Implementation Plan

### Phase 1 (complete)

- [x] Step 1: Fixture JSON + fix `conftest.py` `::`; add per-file budget fixtures.
- [x] Step 2: Hardening — remove router stub; single AsyncOpenAI client; settings-aware chunker.
- [x] Step 3: `PipelineDocument` schemas + adapter + markdown chunker.
- [x] Step 4: Loader + parser + registry; upstream chain test.
- [x] Step 5: `test_milestone_e2e.py` + slow smoke tests.
- [x] Step 6: `ingest_from_dir.py` CLI (`--dry-run`).
- [x] Step 7: preflight, architecture_decision (simplified), inspect_fixtures.
- [x] Step 8: API-collection embeddings request.
- [x] Step 9: README, technical docs, architecture HTML, ADR-001.
- [x] Step 10: Full `uv run pytest`; sync AC + verification.

### Phase 2 (pending — execute in order)

- [ ] Step 11: Commit `data/catalog/catalog.yaml` + `data/seed/` from estimator reference; catalog models + `load_catalog` + tests (RED → GREEN).
- [ ] Step 12: Upgrade `FileSystemLoader` to `LoadedBlob` + `iter_blobs`; settings for `data_root` / `catalog_path`.
- [ ] Step 13: `ParseContext`, `Parser` Protocol, `ParserRegistry`; refactor components JSON parser.
- [ ] Step 14: `normalize_commercial_budget` + commercial parser; golden tests with seed budgets.
- [ ] Step 15: `TranscriptTxtParser` + transcript fixtures; `transcript_docs_to_chunks`.
- [ ] Step 16: `cleaning/` modules + wire in orchestrator for commercial path only.
- [ ] Step 17: `pii/` modules + `InMemoryMappingStore` + wire in orchestrator (setting-gated).
- [ ] Step 18: `orchestrator.py` + `jobs.py` + `run_catalog_ingest` in `ingest.py`.
- [ ] Step 19: HTTP catalog routes + BackgroundTasks + integration tests.
- [ ] Step 20: Expand CLIs (architecture, load_catalog, inspect_corpus); extend `ingest_from_dir`.
- [ ] Step 21: `test_catalog_ingest_e2e.py` + update existing tests for new metadata fields.
- [ ] Step 22: Docs — ADR-001, README, technical README, architecture HTML, `.env.example`.
- [ ] Step 23: Full `uv run pytest`; optional `--run-heavy` PII smoke; sync AC-19..AC-31.

## Learnings

- Estimator `ingestion/` is **upstream** (catalog → document extraction); master-ia `embedding_pipeline/` is **downstream** (chunk → embed). Two explicit stages remain the architecture.
- Prefer component-level chunks (master-ia) over whole-budget documents (estimator) for retrieval granularity; normalize commercial JSON into components rather than embedding one doc per budget file.
- Estimator’s unwired `cleaning/` and `pii/` are an anti-pattern — Phase 2 must call them from `ingest_catalog_source()` before embed.
- The repos use **different budget JSON schemas**; a normalizer is required — do not fork the Session 07 `Budget` model.
- Transcripts are first-class sources (turn/block documents), not budgets — separate chunk path (1:1).
- Keep stdlib logging; keep semantic_cache isolation; keep offline default test suite (stub PII in fast path).
- Markdown template change alters embedding vectors — re-run sanity pairs under `--run-heavy` after Phase 2 if PII or template shifts.
- Phase 2 scope change (2026-06-09): ADR-001 “Deferred” table is superseded for catalog, cleaning, PII, and catalog HTTP — update ADR when implementation starts.

## Open questions

- **Loader depth (Phase 1):** resolved — non-recursive for `iter_budget_files`; Phase 2 `iter_blobs` is **recursive** per estimator.
- **ADR placement:** resolved — `docs/work-items/adr-001-embedding-pipeline-vs-estimator-ingestion.md`.
- **Commercial → component hours heuristic:** default `weeks * 40` unless `amount` present — document in normalizer docstring; revisit if evals show poor retrieval.
- **Transcript source in catalog (`review`):** HTTP must reject until promoted to `include`; CLI may allow `--force` for learning only (default off).
- **PII default:** `embedding_pipeline_pii_enabled=false` in tests and `.env.example`; enable explicitly for demos with salt set.
- **pandas/pandera weight:** acceptable for learning module; lazy-import in cleaning module to keep import time low when unused.

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
- [x] Step 5: `test_milestone_e2e.py` + slow smoke tests
- [x] Step 6: `ingest_from_dir.py` CLI (`--dry-run`)
- [x] Step 7: `preflight`, `architecture_decision`, `inspect_fixtures` CLIs
- [x] Step 8: API-collection embeddings request
- [x] Step 9: README, `docs/technical/README.md`, architecture HTML, ADR-001
- [x] Step 10: Full `uv run pytest`; sync AC + verification

## Pull request

- [WIP] https://github.com/povedica/master-ia-lidr/pull/31 (label: `wip`)

## Deferred to Session 08+ (after Phase 2)

- Vector DB persistence and similarity search over stored chunks.
- Postgres-backed `ingestion_jobs` and `pii_mappings` (replace in-memory stores).
- XLSX / DOCX / PDF parsers and `rate_card_xlsx` catalog source activation.
- Shared low-level OpenAI embeddings client across `semantic_cache` and `embedding_pipeline`.
- Promote `transcripciones_txt` from `review` to `include` after legacy parser sign-off (operational process, not code-only).

## Phase 2 implementation progress

- [ ] Step 11: Data catalog + seed corpus
- [ ] Step 12: Loader upgrade
- [ ] Step 13: Parser protocol + registry refactor
- [ ] Step 14: Commercial budget normalizer
- [ ] Step 15: Transcript parser
- [ ] Step 16: Cleaning wired
- [ ] Step 17: PII wired
- [ ] Step 18: Orchestrator + jobs
- [ ] Step 19: HTTP catalog routes
- [ ] Step 20: CLI expansion
- [ ] Step 21: Catalog e2e tests
- [ ] Step 22: Documentation
- [ ] Step 23: Final verification
