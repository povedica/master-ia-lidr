"""Moderation boundary (provider-backed implementations can replace the stub)."""

from __future__ import annotations

from app.guardrails.contracts import (
    GuardrailLayer,
    GuardrailPolicy,
    GuardrailResult,
    GuardrailSeverity,
)


async def evaluate_moderation_placeholder(_text: str) -> GuardrailResult:
    """Return pass while moderation is disabled; real providers plug in here later."""

    return GuardrailResult(
        guardrail_id="moderation_toxicity",
        layer=GuardrailLayer.INPUT_SEMANTIC,
        passed=True,
        reasons=[],
        severity=GuardrailSeverity.LOW,
        recommended_policy=GuardrailPolicy.EXCEPTION,
        audit_payload={"implementation": "placeholder"},
    )
