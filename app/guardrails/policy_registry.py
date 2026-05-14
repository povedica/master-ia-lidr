"""Central guardrail declarations (metadata and policy defaults)."""

from __future__ import annotations

from app.guardrails.contracts import (
    GuardrailDeclaration,
    GuardrailLayer,
    GuardrailPolicy,
    GuardrailSeverity,
    RolloutMode,
)

_RULES_VERSION = "2026-05-14"

_RAW_DECLARATIONS: tuple[GuardrailDeclaration, ...] = (
    GuardrailDeclaration(
        id="estimation_domain_relevance",
        description="Deterministic estimation-domain relevance and obvious off-topic rejection.",
        layer=GuardrailLayer.INPUT_SEMANTIC,
        severity=GuardrailSeverity.MEDIUM,
        on_fail=GuardrailPolicy.FILTER,
        retry_max=0,
        rollout=RolloutMode.ENFORCE,
        rules_version=_RULES_VERSION,
        metrics_event_name="guardrail_domain_relevance",
    ),
    GuardrailDeclaration(
        id="moderation_toxicity",
        description="Provider moderation or equivalent toxicity screening.",
        layer=GuardrailLayer.INPUT_SEMANTIC,
        severity=GuardrailSeverity.CRITICAL,
        on_fail=GuardrailPolicy.EXCEPTION,
        retry_max=0,
        rollout=RolloutMode.DISABLED,
        rules_version=_RULES_VERSION,
        metrics_event_name="guardrail_moderation",
    ),
    GuardrailDeclaration(
        id="pii_basic",
        description="Deterministic basic PII detection (email, phone, IBAN, etc.).",
        layer=GuardrailLayer.INPUT_SEMANTIC,
        severity=GuardrailSeverity.HIGH,
        on_fail=GuardrailPolicy.EXCEPTION,
        retry_max=0,
        rollout=RolloutMode.LOG_ONLY,
        rules_version=_RULES_VERSION,
        metrics_event_name="guardrail_pii_basic",
    ),
    GuardrailDeclaration(
        id="prompt_injection_patterns",
        description="Deterministic prompt-injection and role-manipulation heuristics.",
        layer=GuardrailLayer.INPUT_SEMANTIC,
        severity=GuardrailSeverity.HIGH,
        on_fail=GuardrailPolicy.EXCEPTION,
        retry_max=0,
        rollout=RolloutMode.LOG_ONLY,
        rules_version=_RULES_VERSION,
        metrics_event_name="guardrail_prompt_injection",
    ),
)

GUARDRAIL_DECLARATIONS: tuple[GuardrailDeclaration, ...] = tuple(
    sorted(_RAW_DECLARATIONS, key=lambda d: d.id),
)


def iter_guardrail_declarations() -> tuple[GuardrailDeclaration, ...]:
    """Return all guardrail declarations sorted by id."""

    return GUARDRAIL_DECLARATIONS
