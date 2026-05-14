"""Resolve effective rollout (registry + optional settings overrides)."""

from __future__ import annotations

from app.config import Settings
from app.guardrails.contracts import GuardrailDeclaration, RolloutMode


def effective_rollout(decl: GuardrailDeclaration, settings: Settings) -> RolloutMode:
    """Return rollout mode, allowing environment-specific overrides per guardrail id."""

    raw = ""
    if decl.id == "pii_basic":
        raw = settings.guardrail_rollout_pii_basic.strip().lower()
    elif decl.id == "prompt_injection_patterns":
        raw = settings.guardrail_rollout_prompt_injection_patterns.strip().lower()
    elif decl.id == "estimation_domain_relevance":
        raw = settings.guardrail_rollout_estimation_domain_relevance.strip().lower()
    elif decl.id == "moderation_toxicity":
        raw = settings.guardrail_rollout_moderation_toxicity.strip().lower()
    elif decl.id == "output_confidence_floor":
        raw = settings.guardrail_rollout_output_confidence_floor.strip().lower()
    elif decl.id == "output_sensitive_leakage":
        raw = settings.guardrail_rollout_output_sensitive_leakage.strip().lower()
    elif decl.id == "output_useless_placeholder":
        raw = settings.guardrail_rollout_output_useless_placeholder.strip().lower()

    if raw in {"", "inherit"}:
        return decl.rollout
    try:
        return RolloutMode(raw)
    except ValueError:
        return decl.rollout
