"""Deterministic basic PII heuristics (no external services)."""

from __future__ import annotations

import re

from app.guardrails.contracts import (
    GuardrailLayer,
    GuardrailPolicy,
    GuardrailResult,
    GuardrailSeverity,
)

_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\w)\+\d{10,15}(?!\w)")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
_DNI_NIE_RE = re.compile(r"\b\d{8}[A-Z]\b|\b[XYZ]\d{7}[A-Z]\b", re.IGNORECASE)
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){15,16}\b")


def _find_matches(pattern: re.Pattern[str], text: str, label: str) -> list[str]:
    found = pattern.findall(text)
    return [label] * len(found)


def evaluate_basic_pii(text: str) -> GuardrailResult:
    """Return a normalized guardrail result when obvious PII-like patterns appear."""

    matched_rules: list[str] = []
    matched_rules.extend(_find_matches(_EMAIL_RE, text, "email"))
    matched_rules.extend(_find_matches(_PHONE_RE, text, "phone_heuristic"))
    matched_rules.extend(_find_matches(_IBAN_RE, text, "iban"))
    matched_rules.extend(_find_matches(_DNI_NIE_RE, text, "dni_nie"))
    matched_rules.extend(_find_matches(_CARD_RE, text, "card_like"))

    passed = not matched_rules
    return GuardrailResult(
        guardrail_id="pii_basic",
        layer=GuardrailLayer.INPUT_SEMANTIC,
        passed=passed,
        reasons=["pii_pattern_detected"] if not passed else [],
        severity=GuardrailSeverity.HIGH if not passed else GuardrailSeverity.LOW,
        matched_rules=matched_rules[:32],
        recommended_policy=GuardrailPolicy.EXCEPTION,
        audit_payload={"matched_types": len(set(matched_rules))},
    )
