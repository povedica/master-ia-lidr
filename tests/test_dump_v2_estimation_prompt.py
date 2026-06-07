"""Dry-run prompt dump script."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.config import Settings
from app.context.examples import load_examples
from app.services.estimation_prompt_rendering import render_estimation_prompt
from scripts.dump_v2_estimation_prompt import (
    build_full_dummy_request,
    build_markdown_report,
    run_dump,
)


def test_build_full_dummy_request_validates() -> None:
    req = build_full_dummy_request()
    assert req.project_name
    assert len(req.deliverables) >= 3
    assert req.attachments


def test_build_markdown_report_includes_system_and_user_sections() -> None:
    request = build_full_dummy_request()
    settings = Settings(_env_file=None, openai_api_key="sk-test")
    rendered = render_estimation_prompt(
        request,
        examples=load_examples(),
        preprocessing="none",
        examples_version="test",
        settings=settings,
    )
    prelude = SimpleNamespace(
        max_output_tokens=2048,
        preprocessed_markdown_for_template=None,
    )
    md = build_markdown_report(
        request=request,
        settings=settings,
        assessment_surface="summary\n\ndescription",
        prelude=prelude,  # type: ignore[arg-type]
        rendered=rendered,
        bundle_version="v2",
    )
    assert "## Message 1 — role: `system`" in md
    assert "## Message 2 — role: `user`" in md
    assert rendered.system_prompt in md
    assert rendered.user_prompt in md


def test_run_dump_writes_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("scripts.dump_v2_estimation_prompt._OUTPUT_DIR", tmp_path)
    fake_prelude = SimpleNamespace(
        preprocessed_markdown_for_template=None,
        max_output_tokens=1024,
    )
    with patch(
        "scripts.dump_v2_estimation_prompt.EstimationService.prepare_structured_prelude",
        new_callable=AsyncMock,
        return_value=fake_prelude,
    ):
        dest = asyncio.run(run_dump(preprocessing="none", prompt_version_override="v2"))
    assert dest.is_file()
    assert "LLM prompt dump" in dest.read_text(encoding="utf-8")
    assert dest.name.startswith("prompt-v2-")
