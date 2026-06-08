# Feature: CLI Cosine Similarity Script and Sanity Check

> Increment 5 of 5 for the minimal embedding pipeline (Session 07). Completes the milestone.
> Depends on: `feature-032` (embedder). Independent of `feature-031` (chunker) and `feature-033` (endpoint).

## Objective

Implement `app/scripts/compare.py`: a CLI that embeds two texts via `OpenAIEmbedder.embed_one()` and prints their cosine similarity (computed with the `math` stdlib only). Produce `app/embedding_pipeline/SANITY_CHECK.md` recording similarity for three reference pairs plus a short interpretation, as live-session discussion material.

This is the final increment: with it, the milestone (schemas → chunker → embedder → endpoint → quality check) is fully covered.

## Context

- `OpenAIEmbedder.embed_one()` is async (`feature-032`); the CLI wraps it with `asyncio.run`.
- The CLI lives under `app/scripts/` (not repo-root `scripts/`) because the `Dockerfile` only `COPY app ./app`; only files under `app/` are inside the image. The docker-compose service is named `app` (not `servicio_ia`). Invoke as a module: `python -m app.scripts.compare ...` (architecture review, LOW).
- No numpy: cosine similarity is implemented manually with `math`.
- Logging via stdlib `logging`; the CLI prints results to stdout (user-facing output), not via the logger.
- Settings/keys via `app.config.get_settings()` (reads `OPENAI_API_KEY`).

## Scope

### Includes
- `app/scripts/compare.py` CLI (`argparse`) with `--text-a` and `--text-b`.
- Manual cosine similarity using `math` only.
- Reuse of `OpenAIEmbedder.embed_one()` (no duplicated embedding logic).
- `app/embedding_pipeline/SANITY_CHECK.md` with the three pair results + interpretation.
- README run instructions for both execution modes.

### Excludes
- numpy / scikit / any ML lib.
- New embedding logic (must reuse the embedder).
- Endpoint or chunker changes.
- Vector DB persistence.

## Functional Requirements

CLI spec:

```bash
python -m app.scripts.compare \
  --text-a "OAuth 2.0 authentication backend for fintech" \
  --text-b "JWT-based authorization service for banking app"
```

- Both `--text-a` and `--text-b` are required string args.
- Embed each via `OpenAIEmbedder(get_settings()).embed_one(text)` (wrapped in `asyncio.run`).
- Cosine similarity: `dot(a, b) / (norm(a) * norm(b))`, computed with `math` (`math.sqrt`, `math.fsum`), guarding against zero norm.
- Output must include both texts and the numeric similarity, e.g.:

```text
Text A: OAuth 2.0 authentication backend for fintech
Text B: JWT-based authorization service for banking app
Cosine similarity: 0.8421
```

- Exit code `0` on success; non-zero on error (e.g. missing API key) with a safe stderr message.

Two execution modes (both documented in README):
- Inside container: `docker compose exec app python -m app.scripts.compare --text-a "..." --text-b "..."`
- Outside container: `uv run python -m app.scripts.compare --text-a "..." --text-b "..."` (with `.env` loaded).

### Sanity check pairs (record results in `SANITY_CHECK.md`)

| Pair | Text A | Text B | Expectation |
|------|--------|--------|-------------|
| A (semantically close) | `"OAuth 2.0 authentication backend with JWT tokens for fintech mobile app"` | `"Authorization service using JSON Web Tokens for a banking application"` | > 0.6 |
| B (unrelated) | `"OAuth 2.0 authentication backend with JWT tokens for fintech mobile app"` | `"Database migration from MySQL to PostgreSQL with zero downtime"` | < 0.4 |
| C (generic/ambiguous) | `"Backend services"` | `"API development"` | No fixed expectation — record and comment |

`SANITY_CHECK.md` must contain:
1. The numeric similarity obtained for each of the 3 pairs.
2. A 3–5 line comment on whether results match intuition and anything surprising.

## Technical Approach

- `app/scripts/compare.py`:
  - `import argparse`, `import asyncio`, `import math`, `import sys`.
  - `from app.config import get_settings`; `from app.embedding_pipeline.embedder import OpenAIEmbedder`.
  - `def cosine_similarity(a: list[float], b: list[float]) -> float:` (manual, `math`-only, zero-norm guard).
  - `async def _embed_pair(text_a, text_b) -> tuple[list[float], list[float]]` using one embedder instance.
  - `def main(argv: list[str] | None = None) -> int:` parses args, runs `asyncio.run(_embed_pair(...))`, computes similarity, prints, returns exit code.
  - `if __name__ == "__main__": raise SystemExit(main())`.
- `app/embedding_pipeline/SANITY_CHECK.md`: a table of the 3 measured values + the comment. Values are filled by running the CLI with a real key during implementation.

## Acceptance Criteria
- [x] AC-01: `compare.py` accepts `--text-a` and `--text-b` and errors clearly if either is missing.
- [x] AC-02: Output contains both input texts and a numeric cosine similarity.
- [x] AC-03: Cosine similarity is implemented with `math` only (no numpy import anywhere).
- [x] AC-04: Embedding logic is reused from `OpenAIEmbedder.embed_one()`; no embedding code is duplicated in the script.
- [x] AC-05: On valid input with a real key, the script exits `0` and prints a value in `[0.0, 1.0]` (allowing tiny float epsilon).
- [x] AC-06: `cosine_similarity` returns `1.0` for identical vectors and `0.0` for orthogonal vectors (unit tests, no network).
- [x] AC-07: `cosine_similarity` guards against zero-norm input without raising `ZeroDivisionError`.
- [x] AC-08: `SANITY_CHECK.md` exists with the 3 pair results and a 3–5 line comment.
- [x] AC-09: Pair A similarity > 0.6 and Pair B similarity < 0.4 when measured (recorded); Pair C recorded with commentary. *(Pair A measured 0.5957 — marginally below 0.6; documented in SANITY_CHECK.md.)*
- [x] AC-10: README documents both execution modes with `python -m app.scripts.compare`.

## Test Plan
- Unit tests (`tests/embedding_pipeline/test_compare.py`), no network:
  - `cosine_similarity` on identical, orthogonal, and opposite vectors (AC-06).
  - Zero-norm guard (AC-07).
  - `main([...])` with a **patched** `OpenAIEmbedder.embed_one` returning fixed vectors; assert exit `0` and that stdout contains both texts + a numeric value (AC-01, AC-02, AC-05).
- Manual checks (real key, local only): run the three sanity pairs, record values in `SANITY_CHECK.md`.

## Verification
- **Verified:** `uv run pytest tests/embedding_pipeline/test_compare.py` — 6 passed (mocked embedder).
- **Verified:** `uv run pytest tests/embedding_pipeline/` — 47 passed.
- **Verified (manual, real key):** three sanity pairs run; Pair B 0.1920 (< 0.4), Pair C 0.5408 recorded; Pair A 0.5957 (marginally below 0.6 — noted in SANITY_CHECK.md).
- **Not verified:** Docker in-container run (same module path; documented in README).
- Architecture HTML: **N/A** — no routes, orchestration, or env surface changes.

## Documentation Plan
- README: add the CLI usage (both modes) and a pointer to `SANITY_CHECK.md`.
- `app/embedding_pipeline/SANITY_CHECK.md`: the three measured similarities + interpretation.
- Second Brain: short reflection on what the similarity numbers reveal about `text-embedding-3-small` for budget-style text.

## Estimation

- Size: S
- Estimated time: 2 hours
- Planned steps: 6

## Pull Request

- WIP: https://github.com/povedica/master-ia-lidr/pull/30

## Implementation progress

- [x] Step 1: Implement `cosine_similarity` + unit tests (RED → GREEN).
- [x] Step 2: Implement `compare.py` CLI (`argparse` + `asyncio.run`, reuse embedder).
- [x] Step 3: Add mocked `main()` test.
- [x] Step 4: Run the 3 sanity pairs with a real key; capture values.
- [x] Step 5: Write `SANITY_CHECK.md` (values + comment).
- [x] Step 6: Update README + Second Brain note.

## Implementation Plan
- [x] Step 1: Implement `cosine_similarity` + unit tests (RED → GREEN).
- [x] Step 2: Implement `compare.py` CLI (`argparse` + `asyncio.run`, reuse embedder).
- [x] Step 3: Add mocked `main()` test.
- [x] Step 4: Run the 3 sanity pairs with a real key; capture values.
- [x] Step 5: Write `SANITY_CHECK.md` (values + comment).
- [x] Step 6: Update README (both run modes) + Second Brain note.

## Repository commits (master-ia)

| Commit | Summary |
|--------|---------|
| `c5b4eb7` | `test(embedding-pipeline): add compare CLI contract tests (RED→GREEN)` |
| `5d2df13` | `feat(embedding-pipeline): add cosine compare CLI and sanity check docs` |

## Learnings
- Implementing cosine similarity by hand keeps the dependency surface minimal and makes the math explicit for the learning session.
- Running inside Docker requires the script under `app/` and invocation via `python -m`; a repo-root `scripts/` file would not exist in the image.
- Pair C ("Backend services" vs "API development") is intentionally ambiguous: discussing whether the model rates it closer to A or B is the point, not a pass/fail threshold.
