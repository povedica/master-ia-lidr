"""Pytest skip markers for eval soft and judge suites."""

from __future__ import annotations

import pytest

from tests.evals.judge.config import judge_credentials_available
from tests.evals.settings import eval_estimator_uses_real_llm

requires_live_estimator = pytest.mark.skipif(
    not eval_estimator_uses_real_llm(),
    reason="set EVAL_ESTIMATOR_USE_REAL_LLM=true with OPENAI_API_KEY for live estimator evals",
)

requires_judge_credentials = pytest.mark.skipif(
    not judge_credentials_available(),
    reason="judge credentials missing: set EVAL_JUDGE_API_KEY or provider API key",
)
