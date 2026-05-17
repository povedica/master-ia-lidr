"""Langfuse generation helpers for the LiteLLM gateway."""

from __future__ import annotations

from app.services.llm_types import UsageInfo
from app.services.observability.types import ObservabilityAdapter
from app.services.observability.usage_cost import cost_details_from_estimate, openai_usage_details

LLM_GENERATION_NAME = "estimator.llm.generate"
STRUCTURED_LLM_GENERATION_NAME = "estimator.llm.structured_output"


def infer_llm_vendor(litellm_model: str) -> str:
    if "/" not in litellm_model:
        return "unknown"
    return litellm_model.split("/", 1)[0]


def generation_metadata_for_litellm(
    *,
    chain_provider: str,
    litellm_model: str,
    llm_vendor: str,
) -> dict[str, str]:
    return {
        "provider": chain_provider,
        "model": litellm_model,
        "llm_vendor": llm_vendor,
    }


def complete_llm_generation(
    observability: ObservabilityAdapter,
    *,
    resolved_model: str,
    usage: UsageInfo | None,
    finish_reason: str,
    output_text: str,
) -> None:
    """Attach usage, optional cost, output, and outcome metadata to the active generation."""

    observability.update_generation_metadata(
        metadata={
            "finish_reason": finish_reason,
            "resolved_model": resolved_model,
        },
    )
    if usage is not None:
        observability.update_generation_usage(openai_usage_details(usage))
        cost = _estimated_cost_usd(_model_for_cost_estimate(resolved_model), usage)
        cost_details = cost_details_from_estimate(cost)
        if cost_details is not None:
            observability.update_generation_cost(cost_details)
    observability.update_generation_output(output_text)


def _model_for_cost_estimate(resolved_model: str) -> str:
    """Map LiteLLM ids (``openai/gpt-4o-mini``) to keys used in ``estimate_cost_usd``."""

    if "/" in resolved_model:
        return resolved_model.split("/", 1)[1]
    return resolved_model


def _estimated_cost_usd(model: str, usage: UsageInfo) -> float | None:
    from app.schemas.estimations import UsageView
    from app.services.estimate_response_builder import estimate_cost_usd

    view = UsageView(
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        preprocessing_input_tokens=usage.preprocessing_input_tokens,
        preprocessing_output_tokens=usage.preprocessing_output_tokens,
    )
    return estimate_cost_usd(model, view)
