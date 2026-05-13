"""Single public entry point for estimation Jinja2 prompts."""

from __future__ import annotations

from app.context.examples import EstimationExample
from app.schemas.estimation_request import EstimationRequest
from app.services.estimation_engine import EstimationMode
from app.services.estimation_request_render import render_estimation_user_message
from app.services.inline_cleaning_prompt import INLINE_CLEANING_BLOCK
from app.services.prompt_context import build_estimation_prompt_context
from app.services.prompt_renderer import PromptRenderer, RenderedPrompt
from app.services.prompt_versions import resolve_prompt_template_set


def render_estimation_prompt(
    request: EstimationRequest,
    *,
    mode: EstimationMode,
    examples: list[EstimationExample],
    preprocessing: str,
    preprocessed_requirements: str | None = None,
    version: str | None = None,
    examples_version: str,
    schema_version: str = "1",
) -> RenderedPrompt:
    """Render versioned system and user prompts from the guided form request."""

    guided = render_estimation_user_message(request)
    if preprocessing == "two_phase" and preprocessed_requirements and preprocessed_requirements.strip():
        estimation_user_message = preprocessed_requirements.strip()
    else:
        estimation_user_message = guided

    inline_block = INLINE_CLEANING_BLOCK if preprocessing == "inline_cleaning" else ""

    template_set = resolve_prompt_template_set("estimation", version)
    context = build_estimation_prompt_context(
        request,
        mode=mode,
        examples=examples,
        estimation_user_message=estimation_user_message,
        preprocessing=preprocessing,
        inline_cleaning_block=inline_block,
        schema_version=schema_version,
    )
    renderer = PromptRenderer()
    return renderer.render(template_set, context, examples_version=examples_version)
