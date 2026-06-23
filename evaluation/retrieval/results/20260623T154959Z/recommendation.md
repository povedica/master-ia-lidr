# Retrieval recommendation

Recommended production candidate: **Mode B**.

Rationale:
- Highest mean precision@5 (0.240) in this run.
- Latency p50 166.4 ms vs baseline mode A (167.2 ms).
- Golden set size is small (5 queries); treat deltas as directional, not statistically significant.

## Reranking trade-off
- Vector + rerank (C) vs vector-only (A): Δ precision@5 -0.120, Δ latency p50 +75.5 ms.
- Hybrid + rerank (D) vs hybrid-only (B): Δ precision@5 -0.120, Δ latency p50 +70.6 ms.

Reranking did not improve mean precision@5 over its non-rerank counterpart in this run; latency cost is not justified on this evidence alone.
