"""Serialize and restore structured estimation bundles for semantic cache."""

from __future__ import annotations

from typing import Any

from app.schemas.estimation_result import EstimationResult
from app.services.estimation_engine import EstimationMode, InputAssessment, ModeEligibility
from app.services.llm_service import StructuredEstimateBundle
from app.services.llm_types import UsageInfo


def structured_bundle_to_artifact_fields(bundle: StructuredEstimateBundle) -> dict[str, Any]:
    """Convert a live bundle into JSON-friendly fields for ``CachedEstimationArtifact``."""

    usage_dict: dict[str, Any] | None = None
    if bundle.usage is not None:
        usage_dict = {
            "prompt_tokens": bundle.usage.prompt_tokens,
            "completion_tokens": bundle.usage.completion_tokens,
            "total_tokens": bundle.usage.total_tokens,
            "preprocessing_input_tokens": bundle.usage.preprocessing_input_tokens,
            "preprocessing_output_tokens": bundle.usage.preprocessing_output_tokens,
        }
    return {
        "result": bundle.result.model_dump(mode="json"),
        "assessment": {
            "detail_level": bundle.assessment.detail_level,
            "recommended_mode": bundle.assessment.recommended_mode.value,
            "reason": bundle.assessment.reason,
        },
        "mode_eligibility": {
            "allowed_modes": [m.value for m in bundle.mode_eligibility.allowed_modes],
            "blocked_modes": [m.value for m in bundle.mode_eligibility.blocked_modes],
            "reason": bundle.mode_eligibility.reason,
        },
        "usage": usage_dict,
        "finish_reason": bundle.finish_reason,
        "degraded": bundle.degraded,
    }


def structured_bundle_from_artifact_fields(
    *,
    artifact: dict[str, Any],
    prompt_version: str,
    examples_version: str,
    model: str,
    provider: str,
    mode: str,
) -> StructuredEstimateBundle:
    """Rebuild a bundle from cached JSON; raises ``ValueError`` when invalid."""

    result = EstimationResult.model_validate(artifact["result"])
    assess_raw = artifact["assessment"]
    assessment = InputAssessment(
        detail_level=str(assess_raw["detail_level"]),
        recommended_mode=EstimationMode(str(assess_raw["recommended_mode"])),
        reason=str(assess_raw["reason"]),
    )
    mel_raw = artifact["mode_eligibility"]
    mode_eligibility = ModeEligibility(
        allowed_modes=tuple(EstimationMode(m) for m in mel_raw["allowed_modes"]),
        blocked_modes=tuple(EstimationMode(m) for m in mel_raw["blocked_modes"]),
        reason=mel_raw.get("reason"),
    )
    usage: UsageInfo | None = None
    u_raw = artifact.get("usage")
    if isinstance(u_raw, dict) and u_raw:
        usage = UsageInfo(
            prompt_tokens=int(u_raw["prompt_tokens"]),
            completion_tokens=int(u_raw["completion_tokens"]),
            total_tokens=int(u_raw["total_tokens"]),
            preprocessing_input_tokens=int(u_raw.get("preprocessing_input_tokens") or 0),
            preprocessing_output_tokens=int(u_raw.get("preprocessing_output_tokens") or 0),
        )
    return StructuredEstimateBundle(
        result=result,
        prompt_version=prompt_version,
        examples_version=examples_version,
        mode=EstimationMode(mode),
        model=model,
        provider=provider,
        usage=usage,
        degraded=bool(artifact.get("degraded", False)),
        finish_reason=artifact.get("finish_reason"),
        assessment=assessment,
        mode_eligibility=mode_eligibility,
    )
