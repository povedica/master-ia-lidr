"""LLM call JSON persistence tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.services import llm_call_persistence


def test_build_llm_call_filename_uses_expected_utc_format() -> None:
    value = llm_call_persistence.build_llm_call_filename(
        datetime(2026, 6, 7, 12, 34, 56, tzinfo=UTC),
        sequence=3,
    )
    assert value == "llm-call-20260607-123456-003.json"


def test_persist_llm_call_record_writes_pretty_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_call_persistence, "_OUTPUT_DIR", tmp_path)
    payload = {
        "recorded_at_utc": "2026-06-07T12:34:56+00:00",
        "call_kind": "chat",
        "preparation": {"api_endpoint": {"method": "POST", "path": "/api/v1/estimate"}},
        "model_request": {"messages": [{"role": "user", "content": "hi"}]},
        "response": {"text": "hello"},
    }

    destination = llm_call_persistence.persist_llm_call_record(payload)

    assert destination.parent == tmp_path
    assert destination.name.startswith("llm-call-")
    assert destination.name.endswith(".json")
    written = json.loads(destination.read_text(encoding="utf-8"))
    assert written == payload


def test_maybe_persist_skips_when_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_call_persistence, "_OUTPUT_DIR", tmp_path)

    class _Settings:
        llm_call_persist_enabled = False

    monkeypatch.setattr(llm_call_persistence, "get_settings", lambda: _Settings())
    result = llm_call_persistence.maybe_persist_llm_call({"call_kind": "chat"})
    assert result is None
    assert list(tmp_path.iterdir()) == []


def test_maybe_persist_writes_when_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_call_persistence, "_OUTPUT_DIR", tmp_path)

    class _Settings:
        llm_call_persist_enabled = True

    monkeypatch.setattr(llm_call_persistence, "get_settings", lambda: _Settings())
    payload = {"call_kind": "chat", "model_request": {}, "response": {"text": "ok"}}
    destination = llm_call_persistence.maybe_persist_llm_call(payload)
    assert destination is not None
    assert destination.exists()


def test_sanitize_request_kwargs_removes_api_key() -> None:
    sanitized = llm_call_persistence.sanitize_request_kwargs(
        {"timeout": 30, "api_key": "secret", "stream": False}
    )
    assert sanitized == {"timeout": 30, "stream": False}


def test_build_llm_call_record_merges_preparation_snapshot() -> None:
    from app.services.llm_call_audit import merge_llm_call_audit, reset_llm_call_audit, restore_llm_call_audit

    token = reset_llm_call_audit()
    try:
        merge_llm_call_audit(
            templates={"prompt_version": "estimation/v2"},
            variables_before_render={"detail_level": "medium"},
        )
        record = llm_call_persistence.build_llm_call_record(
            call_kind="structured",
            model_request={"messages": []},
            response={"structured_output": {}},
        )
        assert record["preparation"]["templates"]["prompt_version"] == "estimation/v2"
        assert record["model_request"] == {"messages": []}
        assert "recorded_at_utc" in record
    finally:
        restore_llm_call_audit(token)


def test_record_acb_orchestration_audit_in_preparation_snapshot() -> None:
    from app.services.llm_call_audit import (
        record_acb_orchestration_audit,
        reset_llm_call_audit,
        restore_llm_call_audit,
    )

    token = reset_llm_call_audit()
    try:
        record_acb_orchestration_audit(
            acb_enabled=True,
            mode="acb",
            role="critic",
            iteration=1,
            prompt_version_acb="acb/v1",
        )
        record = llm_call_persistence.build_llm_call_record(
            call_kind="structured",
            model_request={"response_model": "CriticFeedback", "messages": []},
            response={"structured_output": {}},
        )
        orchestration = record["preparation"]["orchestration"]
        assert orchestration["acb_enabled"] is True
        assert orchestration["mode"] == "acb"
        assert orchestration["acb_role"] == "critic"
        assert orchestration["acb_iteration"] == 1
        assert orchestration["prompt_version_acb"] == "acb/v1"
    finally:
        restore_llm_call_audit(token)


def test_usage_to_dict_handles_none_and_dataclass() -> None:
    from app.services.llm_types import UsageInfo

    assert llm_call_persistence.usage_to_dict(None) is None
    usage = UsageInfo(prompt_tokens=1, completion_tokens=2, total_tokens=3)
    assert llm_call_persistence.usage_to_dict(usage) == {
        "prompt_tokens": 1,
        "completion_tokens": 2,
        "total_tokens": 3,
        "preprocessing_input_tokens": 0,
        "preprocessing_output_tokens": 0,
    }
