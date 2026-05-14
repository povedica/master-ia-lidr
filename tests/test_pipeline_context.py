"""Tests for ``PipelineContext`` and cache metadata contracts."""

from __future__ import annotations

from app.guardrails.contracts import GuardrailLayer, GuardrailPolicy, GuardrailResult, GuardrailSeverity
from app.guardrails.pipeline_context import CacheMetadata, PipelineContext


def test_pipeline_context_avoids_raw_pii_in_audit_payload() -> None:
    """Audit-oriented payloads should use counts or fingerprints, not raw secrets."""

    gr = GuardrailResult(
        guardrail_id="pii_basic",
        layer=GuardrailLayer.INPUT_SEMANTIC,
        passed=False,
        reasons=["pii_pattern_detected"],
        severity=GuardrailSeverity.HIGH,
        recommended_policy=GuardrailPolicy.EXCEPTION,
        audit_payload={"matched_types": 2},
    )
    ctx = PipelineContext(
        request_id="req_test",
        audit_id="aud_test123456",
        user_input="[redacted-length-only]",
        assessment_surface="surface",
        guardrail_rules_version="2026-05-14",
        validation_results=[gr],
    )
    dumped = ctx.model_dump()
    blob = str(dumped)
    assert "@" not in blob
    assert "matched_types" in blob


def test_cache_metadata_defaults() -> None:
    meta = CacheMetadata()
    assert meta.safe_to_cache is False
    assert meta.hit is False
