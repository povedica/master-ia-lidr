"""Strict prompt renderer."""

import pytest

from app.context.examples import EstimationExample
from app.schemas.estimation_request import EstimationRequest
from app.services.estimation_engine import EstimationMode
from app.services.prompt_context import build_prompt_render_context
from app.services.prompt_exceptions import PromptRenderError
from app.services.prompt_renderer import PromptRenderer
from app.services.prompt_versions import mode_partial_template_path, resolve_prompt_template_set
from tests.estimation_fixtures import minimal_estimation_request_dict


def test_renderer_produces_non_empty_prompts_v2() -> None:
    ts = resolve_prompt_template_set("estimation", "v2")
    renderer = PromptRenderer()
    req = EstimationRequest.model_validate(minimal_estimation_request_dict())
    ctx = build_prompt_render_context(
        req,
        template_set=ts,
        mode=EstimationMode.STANDARD,
        examples=[EstimationExample(meeting_summary="s", estimation="e")],
        estimation_user_message="Build a small API with auth.",
        preprocessing="none",
        inline_cleaning_block="",
        schema_version="1",
        use_preprocessed_user_message=False,
        renderer=renderer,
    )
    out = renderer.render(ts, ctx, examples_version="test-examples-v2")
    assert "phases_table" in out.user_prompt
    assert out.prompt_version == "estimation/v2"
    assert "STANDARD mode" in out.system_prompt or "standard" in out.system_prompt.lower()


def test_strict_undefined_raises_on_missing_key() -> None:
    ts = resolve_prompt_template_set("estimation", "v2")
    renderer = PromptRenderer()
    bad_ctx = {
        "mode_partial_template": mode_partial_template_path(ts, EstimationMode.BASIC),
        "inline_cleaning_block": "",
        "examples": [],
    }
    with pytest.raises(PromptRenderError):
        renderer.render(ts, bad_ctx, examples_version="v2")
