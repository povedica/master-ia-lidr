"""Tests for unified system instructions template (replaces per-mode .txt files)."""

from app.services.prompt_renderer import PromptRenderer
from app.services.prompt_versions import resolve_prompt_template_set


def test_system_instructions_template_is_non_empty() -> None:
    ts = resolve_prompt_template_set("estimation", "v2")
    text = PromptRenderer().render_partial(
        ts.system_instructions_template,
        {
            "detail_level": "medium",
            "output_format": "phases_table",
        },
    )
    assert len(text) >= 200
    assert "practical estimation" in text.lower()
    assert "estimation profile (routing)" not in text.lower()
    assert "medium" in text
    assert "phases_table" in text
