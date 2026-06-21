# Retrieval metadata filters for relevance debugging

When comparing retrieval branches, broad corpus queries can hide why a ranking changed. Adding metadata filters to the internal debug endpoint makes the experiment smaller: same query, same branches, but a controlled subset such as `client_sector=finance`, `main_technology=python`, or `year.from=2023`.

Key learning:

- Apply filters before branch ranking and limiting, not after final results, so vector, lexical, and hybrid all diagnose the same candidate universe.
- Keep `/api/v1/search` unchanged for production-like semantic search; use `/api/v1/retrieval-debug` for operator controls.
- Prefer JSONB containment for stable scalar metadata because it can use the existing GIN index on `chunks.metadata`.
- Document array semantics explicitly. Here, `tags` means contains-all, which is stricter and easier to reason about during tuning.
- Treat performance claims separately from correctness. Unit tests can prove SQL shape, but large-corpus planner behavior still needs Compose Postgres and `EXPLAIN`.
