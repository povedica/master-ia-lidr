"""Pytest markers and skips for session integration tests."""

from __future__ import annotations

import pytest

from tests.support.integration_settings import session_integration_uses_real_llm

requires_fake_structured_llm = pytest.mark.skipif(
    session_integration_uses_real_llm(),
    reason=(
        "Test asserts FakeStructuredLLM capture; unset SESSION_INTEGRATION_TEST_USE_REAL_LLM "
        "or run test_sessions_integration_live_smoke only."
    ),
)

requires_real_structured_llm = pytest.mark.skipif(
    not session_integration_uses_real_llm(),
    reason="Set SESSION_INTEGRATION_TEST_USE_REAL_LLM=true and OPENAI_API_KEY for live smoke.",
)
