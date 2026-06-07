"""Unified system instructions partial (no per-mode prompt files)."""

from pathlib import Path

from app.services.prompt_renderer import PromptRenderer
from app.services.prompt_versions import PROMPTS_ROOT, resolve_prompt_template_set


def test_v2_bundle_has_system_instructions_not_modes_dir() -> None:
    v2 = PROMPTS_ROOT / "estimation" / "v2"
    assert (v2 / "partials" / "system_instructions.md.j2").is_file()
    assert not (v2 / "partials" / "modes").exists()


def test_system_instructions_renders_detail_level_and_output_format() -> None:
    ts = resolve_prompt_template_set("estimation", "v2")
    text = PromptRenderer().render_partial(
        ts.system_instructions_template,
        {
            "detail_level": "medium",
            "output_format": "phases_table",
        },
    )
    assert "estimation profile (routing)" not in text.lower()
    assert "medium" in text
    assert "phases_table" in text
