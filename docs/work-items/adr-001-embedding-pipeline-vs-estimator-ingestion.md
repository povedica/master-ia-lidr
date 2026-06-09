# ADR-001: Embedding pipeline vs estimator ingestion

## Context

`master-ia` Session 07 (`app/embedding_pipeline/`) implements chunk → embed for budget JSON.
The reference repo `ai-engineering/estimator/app/ingestion/` implements catalog → loader → parser → `Document` extraction upstream of any vector store.

A 2026-06-08 comparison showed useful patterns in the estimator (markdown framing, preflight CLIs, filesystem loaders) alongside anti-patterns (unwired PII/cleaning modules, 1-doc-per-budget granularity).

## Decision

Adopt **wired, minimal upstream primitives** inside `embedding_pipeline` while keeping master-ia's **component-level chunks** and **OpenAI embedder** as canonical:

| Adopted | Deferred |
|---------|----------|
| `PipelineDocument` intermediate contract | Postgres `ingestion_jobs` + 202/poll |
| Markdown chunk template (1 chunk per component) | YAML data catalog with audit scores |
| `FileSystemLoader` + JSON parser + registry | Presidio / Pandera cleaning (unwired) |
| `run_ingest()` orchestration shared by HTTP + CLI | HTTP catalog `source_name` field |
| Offline CLIs: preflight, inspect, architecture decision | Shared OpenAI client with `semantic_cache` |
| `IngestStats` cost in API response | Persisted ingest + search API (features 037–038) |
| Postgres + pgvector schema baseline (`documents` / `chunks`, Alembic) — feature-036 | Vector indexes (HNSW/IVFFlat), hybrid search |

## Consequences

- Two stages remain explicit: **upstream** (files → `Budget` → `PipelineDocument`) vs **downstream** (chunk → embed).
- Markdown template changes invalidate prior sanity-check vectors; re-measure under `--run-heavy` when needed.
- New modules must appear in an orchestrated path (HTTP, CLI, or test) — no orphan layers.

## Repository commits (master-ia)

- Recorded when feature-035 closes.
