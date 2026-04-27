# check-performance

## Purpose
Look for obvious performance, latency, and cost issues before considering work complete.

## When to Use
- API changes that call external providers.
- Loops, file processing, or data-heavy work.
- LLM features where latency or token cost matters.

## Review Focus
- repeated expensive work
- unnecessary provider calls
- blocking I/O in request paths
- large prompts or avoidable token usage
- N+1 style patterns
- missing caching or batching when clearly useful

## Rules
- Keep this check proportional; do not over-optimise small exercises.
- Call out measurable or likely hotspots, not vague theory.
- For LLM work, include latency and token/cost awareness when relevant.

## Related
- `check-architecture`
- `testing`
- `finish-task`
