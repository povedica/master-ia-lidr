"""Tests for LLM call audit context."""

from __future__ import annotations

from app.services.llm_call_audit import (
    merge_llm_call_audit,
    reset_llm_call_audit,
    restore_llm_call_audit,
    sanitize_variables_for_persistence,
    set_llm_call_api_endpoint,
    snapshot_llm_call_preparation,
)


def test_snapshot_includes_api_endpoint_and_templates() -> None:
    token = reset_llm_call_audit()
    try:
        set_llm_call_api_endpoint(method="POST", path="/api/v2/estimate", request_id="est_abc")
        merge_llm_call_audit(
            templates={"prompt_version": "estimation/v2"},
            variables_before_render={"detail_level": "medium"},
            notes=["test_note"],
        )
        snap = snapshot_llm_call_preparation()
        assert snap["api_endpoint"] == {"method": "POST", "path": "/api/v2/estimate"}
        assert snap["request_id"] == "est_abc"
        assert snap["templates"]["prompt_version"] == "estimation/v2"
        assert snap["variables_before_render"]["detail_level"] == "medium"
        assert "test_note" in snap["notes"]
    finally:
        restore_llm_call_audit(token)


def test_sanitize_variables_omits_large_base64() -> None:
    import base64

    blob = base64.b64encode(b"x" * 200).decode("ascii")
    sanitized = sanitize_variables_for_persistence({"payload": blob})
    assert "omitted" in sanitized["payload"]
