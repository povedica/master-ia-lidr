"""Judge model configuration from EVAL_* environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


class JudgeConfigError(ValueError):
    """Invalid judge configuration."""


@dataclass(frozen=True)
class JudgeConfig:
    provider: str
    model: str
    api_key: str
    threshold_mode: str
    litellm_model: str


def judge_threshold_mode() -> str:
    return os.getenv("EVAL_JUDGE_THRESHOLD_MODE", "warn").strip().lower()


def judge_credentials_available() -> bool:
    try:
        resolve_judge_config()
        return True
    except JudgeConfigError:
        return False


def resolve_judge_config() -> JudgeConfig:
    provider = os.getenv("EVAL_JUDGE_PROVIDER", "openai").strip().lower()
    model = os.getenv("EVAL_JUDGE_MODEL", "gpt-4o-mini").strip()
    threshold_mode = judge_threshold_mode()
    if threshold_mode not in {"warn", "strict"}:
        raise JudgeConfigError("EVAL_JUDGE_THRESHOLD_MODE must be 'warn' or 'strict'")

    explicit_key = os.getenv("EVAL_JUDGE_API_KEY", "").strip()
    if explicit_key:
        api_key = explicit_key
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    else:
        raise JudgeConfigError(f"unsupported EVAL_JUDGE_PROVIDER: {provider!r}")

    if not api_key:
        raise JudgeConfigError(
            "judge API key missing: set EVAL_JUDGE_API_KEY or provider default key"
        )

    litellm_model = f"{provider}/{model}" if "/" not in model else model
    return JudgeConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        threshold_mode=threshold_mode,
        litellm_model=litellm_model,
    )


def configure_judge_env(config: JudgeConfig) -> None:
    """Set provider SDK env vars consumed by LiteLLM / DeepEval."""

    if config.provider == "openai":
        os.environ["OPENAI_API_KEY"] = config.api_key
    elif config.provider == "anthropic":
        os.environ["ANTHROPIC_API_KEY"] = config.api_key
