"""Tests for basic PII guardrail."""

from __future__ import annotations

from app.guardrails.pii import evaluate_basic_pii


def test_detects_email() -> None:
    r = evaluate_basic_pii("Contact ops@example.com for access.")
    assert r.passed is False
    assert "email" in r.matched_rules


def test_detects_iban() -> None:
    r = evaluate_basic_pii("Wire to ES9121000418450200051332 today.")
    assert r.passed is False
    assert "iban" in r.matched_rules


def test_passes_without_matches() -> None:
    r = evaluate_basic_pii("No sensitive tokens in this estimation scope text.")
    assert r.passed is True
