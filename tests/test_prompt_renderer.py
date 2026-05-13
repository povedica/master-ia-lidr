"""Strict prompt renderer."""

import pytest

from app.services.prompt_exceptions import PromptRenderError
from app.services.prompt_renderer import PromptRenderer
from app.services.prompt_versions import resolve_prompt_template_set


def test_renderer_produces_non_empty_prompts() -> None:
    ts = resolve_prompt_template_set("estimation", "v1")
    renderer = PromptRenderer()
    ctx = {
        "mode_system_fragment": "You are a test assistant.",
        "inline_cleaning_block": "",
        "examples": [{"meeting_summary": "s", "estimation": "e"}],
        "schema_version": "1",
        "detail_level": "medium",
        "output_format": "phases_table",
        "estimation_user_message": "Build a small API with auth.",
        "preprocessing": "none",
        "has_attachments": False,
        "attachment_filenames": [],
        "integration_categories": [],
        "hosting_constraints": [],
        "ui_languages": [],
        "delivery_urgency": "standard",
        "target_date": None,
    }
    out = renderer.render(ts, ctx, examples_version="test-examples-v1")
    assert "test assistant" in out.system_prompt.lower()
    assert "phases_table" in out.user_prompt
    assert out.prompt_version == "estimation/v1"


def test_strict_undefined_raises_on_missing_key() -> None:
    ts = resolve_prompt_template_set("estimation", "v1")
    renderer = PromptRenderer()
    bad_ctx = {
        "mode_system_fragment": "x",
        "inline_cleaning_block": "",
        "examples": [],
        # missing schema_version etc.
    }
    with pytest.raises(PromptRenderError):
        renderer.render(ts, bad_ctx, examples_version="v1")
