# Feature: Postgres pgvector and Alembic Baseline for Semantic Search

> Increment 1 of 4 for the production-like semantic search milestone.
> Depends on: `feature-030` through `feature-035` embedding pipeline baseline.

## Objective

Add the persistent database foundation required by the exercise: Postgres with pgvector, async SQLAlchemy, Alembic migrations, and a first versioned schema for `documents` and `chunks`.

This increment does not change the ingest endpoint behavior yet. Its value is a reproducible database layer that can be started, migrated, inspected, and tested before application writes depend on it.

## Context

- The current embedding pipeline is in-memory: `POST /api/v1/embeddings/ingest` chunks `Budget` objects, embeds them through `OpenAIEmbedder`, and returns `EmbeddedChunk` objects plus stats.
- Existing module boundaries are:
  - `app/routers/embeddings.py` for HTTP orchestration.
  - `app/embedding_pipeline/chunker.py` for `JSONStructuralChunker`.
  - `app/embedding_pipeline/embedder.py` for `OpenAIEmbedder`.
  - `app/embedding_pipeline/schemas.py` for Pydantic request/response and chunk models.
- The repo already uses Docker Compose for the API, web UI, Redis Stack, and Redis Insight; there is no Postgres service yet.
- The exercise requires Postgres 16 with pgvector, SQLAlchemy async, Alembic async migrations, and an initial schema without vector indexes.
- Repository standards require settings through `pydantic-settings`, dependencies managed with `uv`, no real secrets, and API versioning under `/api/v1`.

## Scope

### Includes

- Add runtime dependencies:
  - `sqlalchemy>=2.0`
  - `asyncpg>=0.29`
  - `pgvector>=0.3`
  - `alembic>=1.13`
- Add `DATABASE_URL` to typed settings, `.env.example`, and setup docs.
- Add a `postgres` service to `docker-compose.yml` using `pgvector/pgvector:pg16`.
- Add a Postgres volume and healthcheck with `pg_isready`.
- Update the API service to depend on healthy Postgres and receive a `postgresql+asyncpg://...` URL.
- Initialize Alembic with async configuration.
- Configure Alembic `env.py` so it reads `DATABASE_URL` from settings/environment and recognizes pgvector's `vector` type.
- Add SQLAlchemy database setup and ORM/table models for `documents` and `chunks`.
- Add migration `0001_initial_schema.py` that creates the pgvector extension, tables, and non-vector indexes.
- Add focused tests for settings/model metadata where practical.

### Excludes

- Refactoring `POST /api/v1/embeddings/ingest` to persist data.
- Adding `POST /api/v1/search`.
- Adding vector indexes such as HNSW or IVFFlat.
- Adding metadata filters, hybrid search, or Postgres tuning.
- Running real OpenAI calls.
- Backfilling data.

## Functional Requirements

- A developer can start Postgres locally through Docker Compose.
- The database must use image `pgvector/pgvector:pg16`.
- The database name, user, and password for local development are `estimator` placeholders only.
- The API service must receive `DATABASE_URL=postgresql+asyncpg://estimator:estimator@postgres:5432/estimator` in Compose.
- `alembic upgrade head` must create a clean schema on an empty database.
- `alembic downgrade base` should remove the schema created by this migration, where feasible.
- The schema must include:
  - `documents`
  - `chunks`
  - `vector` extension
  - non-vector indexes only
- The baseline verification must include a manual `SELECT version();` or equivalent connection check before depending on Postgres from application code.

## Technical Approach

### Database Configuration

- Add `database_url: str = ""` to `Settings`.
- Add a small DB module, for example `app/database.py`, with:
  - async engine factory from `settings.database_url`
  - `async_sessionmaker`
  - declarative `Base`
  - dependency/helper for async sessions if needed by later features
- Keep DB setup separate from routers so future ingest/search services can depend on it without direct router SQL.

### Docker Compose

- Add:

```yaml
postgres:
  image: pgvector/pgvector:pg16
  environment:
    POSTGRES_DB: estimator
    POSTGRES_USER: estimator
    POSTGRES_PASSWORD: estimator
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U estimator -d estimator"]
```

- Update the existing API service dependency to include:
  - `postgres: { condition: service_healthy }`
- Preserve existing Redis behavior.

### Schema

`documents`:

- `id`: `BigInteger`, primary key
- `source_path`: `Text`, required
- `document_type`: `String`, required
- `ingested_at`: timezone-aware timestamp, default `now()`
- `metadata`: `JSONB`, default empty object
- index `ix_documents_source_path`
- uniqueness policy: enforce one row per `source_path` so duplicate detection can be reliable in the next feature

`chunks`:

- `id`: `BigInteger`, primary key
- `document_id`: FK to `documents.id`, `ON DELETE CASCADE`, required
- `chunk_type`: `String`, required
- `content`: `Text`, required
- `embedding`: `Vector(1536)`, nullable
- `metadata`: `JSONB`, default empty object
- `created_at`: timezone-aware timestamp, default `now()`
- indexes:
  - `ix_chunks_document_id`
  - `ix_chunks_chunk_type`
  - GIN index on `metadata`

### Alembic

- Use async Alembic template.
- In `env.py`, read `DATABASE_URL` from settings/environment.
- Register pgvector type recognition with SQLAlchemy/Alembic so autogenerate and reflection do not misinterpret vector columns.
- Keep migration explicit enough that a reviewer can see `CREATE EXTENSION IF NOT EXISTS vector`.

## Acceptance Criteria

- [ ] AC-01: `uv.lock` and `pyproject.toml` include SQLAlchemy, asyncpg, pgvector, and Alembic via `uv add`.
- [ ] AC-02: `.env.example` documents `DATABASE_URL` with a placeholder Compose value and no secrets.
- [ ] AC-03: `docker-compose.yml` defines a `postgres` service using `pgvector/pgvector:pg16`.
- [ ] AC-04: `postgres` has a working `pg_isready` healthcheck.
- [ ] AC-05: The API service depends on healthy Postgres and receives `DATABASE_URL=postgresql+asyncpg://...`.
- [ ] AC-06: Alembic async configuration can run `alembic upgrade head`.
- [ ] AC-07: Migration creates `CREATE EXTENSION IF NOT EXISTS vector`.
- [ ] AC-08: Migration creates `documents` with the required columns and `ix_documents_source_path`.
- [ ] AC-09: Migration creates `chunks` with FK `ON DELETE CASCADE`, `Vector(1536)`, JSONB metadata, and required non-vector indexes.
- [ ] AC-10: No HNSW, IVFFlat, or other vector index is created.
- [ ] AC-11: A manual `SELECT version();` against the Compose database is documented as passing.
- [ ] AC-12: Existing embedding pipeline tests still pass without requiring a database unless a DB-specific test is explicitly selected.

## Test Plan

- Unit tests:
  - Settings parse `DATABASE_URL` from environment.
  - SQLAlchemy metadata includes `documents` and `chunks` with expected column names and embedding dimension.
- Migration checks:
  - Run `docker compose up -d postgres`.
  - Run `uv run alembic upgrade head`.
  - Inspect tables with `psql` or a SQLAlchemy connection.
- Regression:
  - Run `uv run pytest tests/embedding_pipeline/` to ensure existing in-memory pipeline behavior was not changed by this foundation step.

## Verification

- Automated:
  - `uv run pytest tests/embedding_pipeline/`
  - targeted DB/settings tests added in this feature
- Manual:
  - `docker compose up -d postgres`
  - `docker compose exec postgres psql -U estimator -d estimator -c "SELECT version();"`
  - `uv run alembic upgrade head`
  - inspect `documents` and `chunks`
- Not verified yet:
  - Persisted ingest flow
  - Search endpoint
  - Query examples script

## Documentation Plan

- README:
  - document Postgres service startup
  - document `DATABASE_URL`
  - document migration commands
  - note that vector indexes are intentionally not part of this baseline
- `.env.example`:
  - add placeholder `DATABASE_URL`
- Second Brain:
  - record the schema decisions and the reason for delaying vector indexes.

## Implementation Plan

- [ ] Step 1: Add dependencies with `uv add sqlalchemy asyncpg pgvector alembic`.
- [ ] Step 2: Add typed `DATABASE_URL` setting and `.env.example` placeholder.
- [ ] Step 3: Add Postgres service, volume, healthcheck, and API dependency in Compose.
- [ ] Step 4: Initialize Alembic async configuration and DB metadata module.
- [ ] Step 5: Add ORM/table models for `documents` and `chunks`.
- [ ] Step 6: Add `0001_initial_schema.py` migration.
- [ ] Step 7: Run Postgres startup and migration checks.
- [ ] Step 8: Update README and Second Brain notes.

## Learnings

- Two tables preserve document-level traceability and allow `ON DELETE CASCADE` to keep chunks consistent with their source.
- JSONB metadata keeps the exercise flexible without a migration for every metadata key, while the GIN index leaves a path for later metadata queries.
- `Vector(1536)` is fixed to `text-embedding-3-small`; changing the embedding model later must be treated as a schema/model-version decision.
- No vector index is deliberate: this establishes a sequential-scan baseline before future HNSW/IVFFlat work.

## Estimation

- Size: M
- Estimated time: 3 hours
- Planned steps: 7

## Implementation progress

- [ ] Step 1: Add SQLAlchemy/asyncpg/pgvector/Alembic dependencies
- [ ] Step 2: Add typed `DATABASE_URL` setting and `.env.example`
- [ ] Step 3: Add Postgres service, volume, healthcheck, and API dependency in Compose
- [ ] Step 4: Add `app/database.py` and ORM models for `documents` and `chunks`
- [ ] Step 5: Initialize Alembic async config and `0001_initial_schema.py` migration
- [ ] Step 6: Add focused settings/model tests
- [ ] Step 7: Update README and run Postgres/migration verification

## Pull Request

- To be filled during `/start-task`.
