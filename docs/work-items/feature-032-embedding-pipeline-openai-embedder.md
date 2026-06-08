# Feature: OpenAI Embedder with Batching and Retry

> Increment 3 of 5 for the minimal embedding pipeline (Session 07).
> Depends on: `feature-030` (schemas). Independent of `feature-031` (chunker).

## Objective

Implement `OpenAIEmbedder` in `app/embedding_pipeline/embedder.py`: call the OpenAI embeddings API (`text-embedding-3-small`, 1536 dims) and return `EmbeddedChunk` objects, with batched requests, bounded retry on rate limits, per-batch structured logging, and a cost estimate.

## Context

- Schemas (`Chunk`, `EmbeddedChunk`) come from `feature-030`.
- The repo is fully async: handlers and the existing embedding adapter use `AsyncOpenAI` (`app/services/semantic_cache/openai_embeddings.py`). **The embedder is async** (`async def embed_one`, `async def embed_many`) using `AsyncOpenAI` + `asyncio.sleep` for backoff.
  - Deviation from exercise text: the exercise specifies synchronous signatures. Architecture review flagged (HIGH) that a synchronous network client inside FastAPI's async route blocks the event loop. We adopt async to stay consistent with the repo and avoid that defect; the CLI (Feature 034) wraps calls in `asyncio.run`.
- Logging: stdlib `logging.getLogger(__name__)` with `extra={...}` (no `structlog`; see `feature-031` Context).
- Existing embedding code: `app/services/semantic_cache/embeddings.py` defines an `EmbeddingProvider` Protocol and a deterministic `FakeEmbeddingProvider`. Reuse that **fake** pattern for tests (architecture review, MEDIUM). Do not import or modify the semantic-cache production adapter; this module stays isolated.

## Scope

### Includes
- `OpenAIEmbedder` class in `app/embedding_pipeline/embedder.py`.
- Module-level constants: `EMBEDDING_MODEL`, `COST_PER_MILLION_TOKENS`, `DEFAULT_BATCH_SIZE`.
- Async public methods `embed_one(text) -> list[float]` and `embed_many(chunks) -> list[EmbeddedChunk]`.
- Batched API calls, rate-limit retry with exponential backoff, per-batch logging, cost calculation.
- New optional settings + `.env.example` entries for embedding model and batch size.

### Excludes
- Chunking (Feature 031), routes (Feature 033), CLI (Feature 034).
- Overriding embedding `dimensions` (use model default 1536).
- numpy/scikit/any ML lib.
- Vector DB persistence.

## Functional Requirements

- Module constants:
  - `EMBEDDING_MODEL = "text-embedding-3-small"`.
  - `COST_PER_MILLION_TOKENS = 0.02`  # USD; pricing subject to change.
  - `DEFAULT_BATCH_SIZE = 100`.
- `OpenAIEmbedder.__init__(self, settings: Settings)`:
  - Read `openai_api_key`, embedding model (settings override, default `EMBEDDING_MODEL`), batch size (settings override, default `DEFAULT_BATCH_SIZE`), and `openai_timeout_seconds` from `Settings`.
  - Raise a clear error at call time if `openai_api_key` is empty (mirror existing adapter behavior).
- `async def embed_one(self, text: str) -> list[float]`:
  - Single embedding; returns a list of 1536 floats.
- `async def embed_many(self, chunks: list[Chunk]) -> list[EmbeddedChunk]`:
  - Call the API in batches of `batch_size` (one request per batch, **not** one per chunk).
  - Preserve input order; map each returned vector back to its `Chunk`, producing `EmbeddedChunk` (copy all `Chunk` fields + `embedding`).
- Retry: catch `openai.RateLimitError`, retry up to 3 times with backoff `1s, 2s, 4s` (`asyncio.sleep`). Re-raise on final failure. Propagate all other exceptions unchanged.
- Per-batch INFO log with stable keys: `batch_index`, `batch_size`, `batch_tokens` (sum of `chunk.token_count` in the batch), `latency_ms` (wall-clock of the API call).
- Cost: accumulate `total_tokens` across batches and expose `last_cost_usd` attribute = `total_tokens / 1_000_000 * COST_PER_MILLION_TOKENS`. Also expose `last_total_tokens`. Document this on the class docstring. (Feature 033 reads these for `IngestStats`.)

Edge cases:
- `embed_many([])` returns `[]`, sets `last_total_tokens = 0`, `last_cost_usd = 0.0`, makes no API call.
- A returned vector whose length is not 1536 is a hard error (raise), since dimensions are not overridden.

## Technical Approach

- `app/embedding_pipeline/embedder.py`:
  - `import asyncio`, `import logging`, `import math` (finite checks), `from time import perf_counter`.
  - `from openai import AsyncOpenAI, RateLimitError`.
  - `from app.config import Settings`; `from app.embedding_pipeline.schemas import Chunk, EmbeddedChunk`.
  - `logger = logging.getLogger(__name__)`.
  - Private `async def _embed_batch(self, texts: list[str]) -> list[list[float]]` containing the retry/backoff loop and per-batch logging.
  - `embed_one` delegates to `_embed_batch([text])[0]`.
  - `embed_many` slices `chunks` into batches, calls `_embed_batch`, zips vectors to chunks, accumulates tokens/cost.
- New settings (in `app/config.py`), both optional with defaults so the feature works with no extra env:
  - `embedding_pipeline_model: str = "text-embedding-3-small"`.
  - `embedding_pipeline_batch_size: int = Field(default=100, ge=1, le=2048)`.
- `.env.example`: add `EMBEDDING_PIPELINE_MODEL=text-embedding-3-small` and `EMBEDDING_PIPELINE_BATCH_SIZE=100` with a short comment block referencing this feature.

## Acceptance Criteria
- [ ] AC-01: `EMBEDDING_MODEL`, `COST_PER_MILLION_TOKENS`, `DEFAULT_BATCH_SIZE` exist as module-level constants with the specified values.
- [ ] AC-02: `embed_one("OAuth 2.0 authentication backend for fintech")` returns a list of exactly 1536 floats.
- [ ] AC-03: All returned floats are finite (no NaN, no Inf).
- [ ] AC-04: `embed_many` issues `ceil(len(chunks)/batch_size)` API calls (verified via mock), not one per chunk.
- [ ] AC-05: Output order of `embed_many` matches input order; each `EmbeddedChunk` keeps its source `Chunk` fields plus `embedding`.
- [ ] AC-06: On `RateLimitError`, the embedder retries up to 3 times with `1/2/4s` backoff, then re-raises; other errors propagate immediately.
- [ ] AC-07: One INFO log per batch with keys `batch_index`, `batch_size`, `batch_tokens`, `latency_ms`.
- [ ] AC-08: `last_total_tokens` and `last_cost_usd` reflect summed token counts and the cost formula after `embed_many`.
- [ ] AC-09: `embed_many([])` returns `[]` with zeroed cost/tokens and no API call.
- [ ] AC-10: Methods are `async`; no synchronous OpenAI client is used.
- [ ] AC-11: No import of `app/services/semantic_cache/*`.

## Test Plan
- Unit tests (`tests/embedding_pipeline/test_embedder.py`), all mocked (no real API keys, per testing rules):
  - Mock `AsyncOpenAI.embeddings.create` to return deterministic 1536-length vectors; assert AC-02/AC-03/AC-05.
  - Assert call count for a 250-chunk / batch-100 case == 3 (AC-04).
  - Simulate `RateLimitError` twice then success; assert 3 attempts and backoff via patched `asyncio.sleep` (AC-06).
  - Assert a non-rate-limit error propagates without retry (AC-06).
  - Assert per-batch log keys with `caplog` (AC-07).
  - Assert `last_total_tokens` / `last_cost_usd` math and the empty-input path (AC-08, AC-09).
- Integration tests: optional, behind a real-key marker; default suite stays offline.
- Manual checks (real key, local only): `embed_one(...)` returns 1536 finite floats.

## Verification
- Automated: `uv run pytest tests/embedding_pipeline/test_embedder.py` (mocked).
- Manual (optional, real key): one `embed_one` call; confirm length 1536 and finite values.
- Not verified yet: endpoint orchestration (Feature 033), CLI (Feature 034).

## Documentation Plan
- README: document `EMBEDDING_PIPELINE_MODEL` / `EMBEDDING_PIPELINE_BATCH_SIZE` and the async embedder contract (`embed_one`/`embed_many`, `last_cost_usd`).
- `.env.example`: new entries with comments.
- Second Brain: note the async deviation from the exercise and the batching/retry design.

## Estimation

- Size: M
- Estimated time: 2.5 hours
- Planned steps: 6

## Implementation progress

- [x] Step 1: Add settings + `.env.example` entries.
- [ ] Step 2: Add `tests/embedding_pipeline/test_embedder.py` with mocked client (RED).
- [ ] Step 3: Implement constants, `__init__`, `_embed_batch` (retry/backoff/log).
- [ ] Step 4: Implement `embed_one` and `embed_many` (batching, ordering, cost).
- [ ] Step 5: Run tests to green; finite-value and ordering assertions.
- [ ] Step 6: Update README + Second Brain note.

## Implementation Plan
- [x] Step 1: Add settings + `.env.example` entries.
- [ ] Step 2: Add `tests/embedding_pipeline/test_embedder.py` with mocked client (RED).
- [ ] Step 3: Implement constants, `__init__`, `_embed_batch` (retry/backoff/log).
- [ ] Step 4: Implement `embed_one` and `embed_many` (batching, ordering, cost).
- [ ] Step 5: Run tests to green; finite-value and ordering assertions.
- [ ] Step 6: Update README + Second Brain note.

## Pull request

- WIP draft PR URL: https://github.com/povedica/master-ia-lidr/pull/27

## Learnings
- Async is the correct boundary here: the existing semantic-cache adapter and all FastAPI routes are async; a blocking client would stall the event loop under concurrency.
- Keep `dimensions` at the model default (1536). Overriding it would silently break the sanity check and any later vector store assumptions.
- Cost is an estimate from a hardcoded price constant; treat it as indicative, not billing-accurate.
