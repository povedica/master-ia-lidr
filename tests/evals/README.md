# Session estimation evals

Pyramid-shaped evaluation suite for multi-turn session estimates.

See the full guide: [docs/evals/session-estimation-evals.md](../../docs/evals/session-estimation-evals.md).

## Quick commands

```bash
# Hard deterministic evals only (no API keys)
uv run pytest tests/evals -m "evals and not slow"

# Full eval folder (skips slow/judge without credentials)
uv run pytest tests/evals

# Judge tests (requires EVAL_ESTIMATOR_USE_REAL_LLM and judge credentials)
EVAL_ESTIMATOR_USE_REAL_LLM=true EVAL_JUDGE_API_KEY=... uv run pytest -m judge
```
