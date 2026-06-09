# Embedding Pipeline Sanity Check

Cosine similarity between text pairs using `text-embedding-3-small` via `python -m app.scripts.compare`.
Measured on 2026-06-08 with a live OpenAI API key.

> **Note (feature-035, 2026-06-09):** The chunk text template changed from flat prose to markdown
> sections. Similarity scores below were measured with the **previous** template; re-run pairs under
> `uv run pytest -m slow tests/embedding_pipeline/ --run-heavy` or the compare CLI if you need
> post-template baselines.

| Pair | Text A | Text B | Similarity | Expectation |
|------|--------|--------|------------|-------------|
| A (semantically close) | OAuth 2.0 authentication backend with JWT tokens for fintech mobile app | Authorization service using JSON Web Tokens for a banking application | **0.5957** | > 0.6 |
| B (unrelated) | OAuth 2.0 authentication backend with JWT tokens for fintech mobile app | Database migration from MySQL to PostgreSQL with zero downtime | **0.1920** | < 0.4 |
| C (generic/ambiguous) | Backend services | API development | **0.5408** | No fixed threshold |

## Interpretation

Pair A lands just below the 0.6 exercise threshold (0.5957), even though the texts clearly share OAuth/JWT/fintech/banking semantics. That gap is small enough to treat as model noise or wording sensitivity rather than a broken pipeline — reruns or slightly different phrasing can cross 0.6.

Pair B (0.1920) is well below 0.4, confirming the model separates auth topics from database migration as expected.

Pair C (0.5408) sits in the middle: both phrases are generic backend vocabulary, so the model rates them as moderately related — closer to Pair A than Pair B, but without a crisp semantic anchor. This is the intended discussion point for the session: short, ambiguous strings produce unstable, context-dependent scores.

Run the CLI yourself:

```bash
uv run python -m app.scripts.compare --text-a "..." --text-b "..."
```
