"""Map provider usage and cost into Langfuse generation payloads."""

from __future__ import annotations

from app.services.llm_types import UsageInfo

_USAGE_FIELD_MAP: dict[str, str] = {
    "prompt_tokens": "prompt_tokens",
    "completion_tokens": "completion_tokens",
    "total_tokens": "total_tokens",
    "preprocessing_input_tokens": "preprocessing_input_tokens",
    "preprocessing_output_tokens": "preprocessing_output_tokens",
}


def openai_usage_details(usage: UsageInfo | dict[str, int | None]) -> dict[str, int]:
    """Build OpenAI-compatible ``usage_details`` for Langfuse generations."""

    if isinstance(usage, UsageInfo):
        source: dict[str, int | None] = {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            "preprocessing_input_tokens": usage.preprocessing_input_tokens,
            "preprocessing_output_tokens": usage.preprocessing_output_tokens,
        }
    else:
        source = usage

    details: dict[str, int] = {}
    for source_key, target_key in _USAGE_FIELD_MAP.items():
        value = source.get(source_key)
        if value is None:
            continue
        int_value = int(value)
        if source_key.startswith("preprocessing_") and int_value == 0:
            continue
        details[target_key] = int_value
    return details


def cost_details_from_estimate(estimated_cost_usd: float | None) -> dict[str, float] | None:
    """Return explicit ``cost_details`` when USD cost is trustworthy."""

    if estimated_cost_usd is None:
        return None
    if estimated_cost_usd < 0:
        raise ValueError("estimated_cost_usd cannot be negative")
    return {"total": float(estimated_cost_usd)}
