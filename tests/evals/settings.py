"""Settings helpers for session estimation eval pytest runs."""

from __future__ import annotations

import os

from app.config import Settings


class EvalTestConfigError(ValueError):
    """Invalid combination of eval test environment variables."""


def eval_estimator_uses_real_llm() -> bool:
    raw = os.getenv("EVAL_ESTIMATOR_USE_REAL_LLM", "false").strip().lower()
    return raw in {"true", "1", "yes"}


def eval_test_settings() -> Settings:
    """Build Settings for ``tests/evals`` from environment."""

    loaded = Settings()
    model_override = os.getenv("EVAL_ESTIMATOR_MODEL", "").strip()
    model = model_override or loaded.openai_model
    updates: dict[str, object] = {
        "openai_model": model,
        "llm_domain_guardrail_enabled": False,
        "semantic_cache_enabled": False,
        "max_attachment_context_chars": 8_000,
    }
    if eval_estimator_uses_real_llm():
        if not loaded.openai_api_key.strip():
            raise EvalTestConfigError(
                "OPENAI_API_KEY is required when EVAL_ESTIMATOR_USE_REAL_LLM=true"
            )
    else:
        updates["openai_api_key"] = "test-key"
    return loaded.model_copy(update=updates)
