# Feature: Semantic Search Query Examples and Production-Like README Evidence

> Increment 4 of 4 for the production-like semantic search milestone.
> Depends on: `feature-036`, `feature-037`, and `feature-038`.

## Objective

Close the semantic search milestone with reproducible evidence: a `query_examples.py` script that exercises `POST /api/v1/search` with representative queries, an `output_examples.txt` artifact captured from a real run, and a concise README section that justifies the exercise's design decisions.

This increment proves that the system behaves end to end without expanding the implementation scope beyond the exercise.

## Context

- `feature-036` adds Postgres + pgvector + Alembic schema.
- `feature-037` persists budget documents and chunk embeddings transactionally.
- `feature-038` exposes semantic search by SQL `cosine_distance`.
- The previous Session 07 CLI `app/scripts/compare.py` compared two strings locally; this milestone requires a higher-level script that calls the HTTP search endpoint against the persisted corpus.
- The official exercise asks for:
  - `query_examples.py`
  - `output_examples.txt`
  - a README section, maximum about one page, justifying:
    - two tables vs one
    - JSONB vs fully typed metadata columns
    - `cosine_distance` vs L2 or inner product
    - no vector index yet

## Scope

### Includes

- Add `query_examples.py` as an executable script.
- The script calls the search endpoint with five query types:
  1. direct known component match
  2. semantic reformulation
  3. unrelated domain
  4. short/ambiguous query
  5. specific technical query
- Format top-5 results in terminal with:
  - `chunk_id`
  - `distance` with four decimals
  - `chunk_type`
  - first about 120 characters of `content`
- Capture a real run in `output_examples.txt`.
- Update README with setup/run instructions and design rationale.
- Add lightweight tests for formatting and script behavior without requiring a live API.

### Excludes

- Ranking evaluation metrics.
- Benchmarking.
- New search features.
- Vector indexes.
- Metadata filters.
- Hybrid search.
- Real OpenAI calls in default tests.
- A separate web UI for search.

## Functional Requirements

### Script Command

The intended Docker command is:

```bash
docker compose run --rm app python query_examples.py
```

If the final service name is renamed to `ai_service` during earlier features, document and use:

```bash
docker compose run --rm ai_service python query_examples.py
```

The script should also support local execution with:

```bash
uv run python query_examples.py
```

### Script Behavior

- Default API base URL:
  - inside Compose: `http://app:8000` or the service DNS name chosen by the implementation
  - local override through an environment variable such as `API_BASE_URL`
- For each query:
  - send `POST /api/v1/search`
  - request `k=5`
  - print a clear heading with the query type and text
  - print each result as one concise line
- If the API returns an error, exit non-zero with a safe message.
- If no results are returned, print an explicit empty result message for that query.

### Query Set

Use queries aligned with the sample budget corpus:

- Direct known component:
  - `"OAuth 2.0 authentication backend with JWT tokens for fintech mobile app"`
- Semantic reformulation:
  - `"Authorization service for a banking application"`
- Unrelated domain:
  - `"Restaurant interior design and kitchen equipment procurement"`
- Ambiguous query:
  - `"Backend services"`
- Specific technical query:
  - `"FastAPI PostgreSQL migration with async SQLAlchemy and API integration"`

The exact query text may be adjusted to match the repo's fixture corpus, but the five categories must remain.

### Output Artifact

`output_examples.txt` must contain:

- command used
- timestamp or date of run
- five query sections
- top-5 output per query where available
- distances formatted to four decimals

Do not include API keys, environment dumps, or sensitive data.

## Technical Approach

### Script Location

Prefer repo root `query_examples.py` because the exercise names it directly. Ensure the Docker image copies it into the app container. If the current Dockerfile only copies `app/`, either:

- update Dockerfile to copy `query_examples.py`, or
- place implementation under `app/scripts/query_examples.py` and add a tiny root wrapper

The public command should still be `python query_examples.py`.

### Implementation

Use standard library first:

- `urllib.request` or `http.client` for HTTP calls, unless the repo already uses `httpx` in runtime dependencies.
- `json`
- `os`
- `textwrap`
- `datetime`
- `sys`

Keep the script small and deterministic. It should consume the API contract from `feature-038`, not duplicate database SQL.

### README Section

Add a concise section such as "Semantic Search with pgvector" covering:

- setup:
  - `docker compose up --build`
  - `uv run alembic upgrade head` or the chosen container command
  - ingest a sample budget
  - run `query_examples.py`
- endpoint summary:
  - `POST /api/v1/embeddings/ingest`
  - `POST /api/v1/search`
- design rationale:
  - two tables
  - JSONB metadata
  - cosine distance
  - no vector index yet
- explicit out-of-scope:
  - HNSW/IVFFlat
  - filters
  - hybrid search
  - tuning

## Acceptance Criteria

- [x] AC-01: `query_examples.py` exists and is executable through the documented Docker command.
- [x] AC-02: The script sends five `POST /api/v1/search` requests, one per required query category.
- [x] AC-03: Each request uses `k=5`.
- [x] AC-04: Terminal output includes query category, query text, and top results.
- [x] AC-05: Each result line includes `chunk_id`, `distance` to four decimals, `chunk_type`, and a truncated content preview.
- [x] AC-06: API errors cause a non-zero exit with a safe message.
- [x] AC-07: `output_examples.txt` captures a real run against the persisted sample corpus.
- [x] AC-08: `output_examples.txt` contains no secrets.
- [x] AC-09: README contains a concise semantic-search section with setup, endpoint usage, and design rationale.
- [x] AC-10: README explicitly states that vector indexes, metadata filters, hybrid search, and tuning are out of scope for this exercise.
- [x] AC-11: Formatting/unit tests for the script pass without live API or OpenAI credentials.
- [x] AC-12: Manual end-to-end verification from Postgres startup through query examples is documented.

## Test Plan

- Unit tests:
  - formatting of one result line
  - content truncation to about 120 characters
  - request payload shape for `k=5`
  - API error handling maps to non-zero exit
- Manual checks:
  - start Compose stack
  - run migrations
  - ingest sample budget(s)
  - run `python query_examples.py`
  - save output to `output_examples.txt`
  - inspect output for five categories and top-k results
- Documentation checks:
  - README commands match actual service names and file paths
  - README rationale stays concise and does not claim vector index support

## Verification

- **Verified (automated, 2026-06-09):**
  - `uv run pytest tests/embedding_pipeline/test_query_examples.py` — 13 passed
  - `uv run pytest tests/embedding_pipeline/test_search_*.py` — 20 passed
  - `uv run pytest` — full suite green (494+ passed, slow deselected)
- **Verified (manual, 2026-06-09):**
  - Compose stack healthy (`app`, `postgres`)
  - `docker compose run --rm app python query_examples.py` — five query sections, top-5 each
  - `output_examples.txt` regenerated from Docker run against persisted fixture corpus
  - README § Semantic search with pgvector documents Postgres → migrate → ingest → query flow
- **Not verified:**
  - future indexed search performance
  - metadata filtering
  - hybrid search quality
- **Residual risk:** duplicate ingests (feature-037/038) still occupy multiple top-k slots in demo output; unrelated queries show high distances (~0.75) without a calibrated threshold.

## Documentation Plan

- README:
  - one-page-style design rationale
  - reproduction commands
  - links or references to `output_examples.txt`
- `output_examples.txt`:
  - generated artifact from the script
- Second Brain:
  - reflect on observed rankings for direct, reformulated, unrelated, ambiguous, and technical queries.

## Implementation Plan

- [x] Step 1: Add script tests for formatting, payloads, and error handling.
- [x] Step 2: Implement `query_examples.py` using the search HTTP API.
- [x] Step 3: Ensure Docker execution path works.
- [x] Step 4: Run the full milestone manually: Postgres, migration, ingest, search examples.
- [x] Step 5: Capture `output_examples.txt`.
- [x] Step 6: Update README and Second Brain notes.
- [x] Step 7: Run final focused validation.

## Learnings

- The script is a smoke test and demo artifact, not a benchmark. It should make behavior visible enough for the live session without pretending to measure retrieval quality rigorously.
- The unrelated and ambiguous queries are as important as the direct match because they reveal distance ranges and ranking uncertainty.
- The README should justify design trade-offs in reviewer language, not just list commands.

## Estimation

- Size: S
- Estimated time: 2 hours
- Planned steps: 7

## Implementation progress

- [x] Step 1: Script unit tests (formatting, payload, error handling)
- [x] Step 2: Implement `query_examples.py` against search HTTP API
- [x] Step 3: Dockerfile copy path for Docker execution
- [x] Step 4: Manual E2E — Postgres, migration, ingest, script
- [x] Step 5: Capture `output_examples.txt` from real run
- [x] Step 6: README semantic-search section + Second Brain notes
- [x] Step 7: Final validation and closure

## Pull Request

- https://github.com/povedica/master-ia-lidr/pull/35 — WIP draft (feature-039)

## Repository commits (master-ia)

| Commit | Summary |
|--------|---------|
| (pending) | docs(feature-039): work item intake |
| (pending) | feat(search): query_examples script, tests, Docker path |
| (pending) | docs(feature-039): README section, output_examples.txt, session note |
