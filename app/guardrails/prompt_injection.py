"""Deterministic prompt-injection heuristics (cheap, before provider calls)."""

from __future__ import annotations

import re

from app.guardrails.contracts import (
    GuardrailLayer,
    GuardrailPolicy,
    GuardrailResult,
    GuardrailSeverity,
)

_INJECTION_PHRASES: tuple[tuple[str, str], ...] = (
    ("phrase_ignore_previous", "ignore previous instructions"),
    ("phrase_ignore_all", "ignore all instructions"),
    ("phrase_you_are_now", "you are now"),
    ("phrase_system_prompt", "system prompt"),
    ("phrase_developer_message", "developer message"),
    ("phrase_end_system", "</system>"),
    ("phrase_begin_system", "<system"),
    ("phrase_role_user", "<|user|>"),
    ("phrase_role_assistant", "<|assistant|>"),
)

_JAILBREAK_HINTS: tuple[tuple[str, str], ...] = (
    ("jailbreak_dan", "dan mode"),
    ("jailbreak_bypass", "bypass safety"),
)


def evaluate_prompt_injection(combined_text: str) -> GuardrailResult:
    """Return a normalized guardrail result for prompt-injection patterns."""

    text = combined_text.lower()
    matched: list[str] = []
    for rule_id, phrase in _INJECTION_PHRASES:
        if phrase in text:
            matched.append(rule_id)
    for rule_id, phrase in _JAILBREAK_HINTS:
        if phrase in text:
            matched.append(rule_id)
    if re.search(r"\bnew\s+instructions\s*:", text):
        matched.append("pattern_new_instructions_colon")

    passed = not matched
    return GuardrailResult(
        guardrail_id="prompt_injection_patterns",
        layer=GuardrailLayer.INPUT_SEMANTIC,
        passed=passed,
        reasons=["prompt_injection_pattern"] if not passed else [],
        severity=GuardrailSeverity.HIGH if not passed else GuardrailSeverity.LOW,
        matched_rules=matched,
        recommended_policy=GuardrailPolicy.EXCEPTION,
        audit_payload={"matched_rule_count": len(matched)},
    )
