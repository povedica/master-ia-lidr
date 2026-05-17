"""Single public entry point for estimation Jinja2 prompts."""

from __future__ import annotations

from app.config import Settings
from app.context.examples import EstimationExample
from app.schemas.estimation_request import EstimationRequest
from app.services.estimation_engine import EstimationMode
from app.services.prompt_context import build_prompt_render_context, build_request_render_context
from app.services.prompt_renderer import PromptRenderer, RenderedPrompt
from app.services.prompt_versions import (
    PromptTemplateSet,
    resolve_prompt_bundle_version,
    resolve_prompt_template_set,
)


def _resolve_version(version: str | None, settings: Settings | None) -> str:
    if version is not None and version.strip():
        return version.strip()
    if settings is not None:
        return resolve_prompt_bundle_version(settings)
    return resolve_prompt_template_set("estimation", None).version


def _template_set(version: str | None, settings: Settings | None) -> PromptTemplateSet:
    return resolve_prompt_template_set("estimation", _resolve_version(version, settings))


def _inline_cleaning_block(
    template_set: PromptTemplateSet,
    preprocessing: str,
    renderer: PromptRenderer,
) -> str:
    if preprocessing != "inline_cleaning":
        return ""
    return renderer.render_partial(template_set.inline_cleaning_template, {})


def render_guided_user_message(
    request: EstimationRequest,
    *,
    version: str | None = None,
    settings: Settings | None = None,
) -> str:
    """Render guided-form Markdown body (tests, cache, guardrails)."""

    template_set = _template_set(version, settings)
    renderer = PromptRenderer()
    ctx = build_request_render_context(request)
    text = renderer.render_partial(template_set.guided_request_template, ctx)
    return text.strip() + "\n"


def render_assessment_surface(
    request: EstimationRequest,
    *,
    version: str | None = None,
    settings: Settings | None = None,
) -> str:
    """Render narrow assessment text for guardrails and mode heuristics."""

    template_set = _template_set(version, settings)
    renderer = PromptRenderer()
    ctx = build_request_render_context(request)
    return renderer.render_partial(template_set.assessment_surface_template, ctx)


def render_two_phase_extraction_system_prompt(
    *,
    version: str | None = None,
    settings: Settings | None = None,
) -> str:
    """System prompt for two-phase requirement extraction."""

    template_set = _template_set(version, settings)
    return PromptRenderer().render_partial(template_set.two_phase_extraction_system_template, {})


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
    settings: Settings | None = None,
) -> RenderedPrompt:
    """Render versioned system and user prompts from the guided form request."""

    template_set = _template_set(version, settings)
    renderer = PromptRenderer()
    guided = render_guided_user_message(request, version=template_set.version)

    use_preprocessed = preprocessing == "two_phase" and preprocessed_requirements
    if use_preprocessed:
        estimation_user_message = preprocessed_requirements.strip()
    else:
        estimation_user_message = guided.strip()

    inline_block = _inline_cleaning_block(template_set, preprocessing, renderer)
    context = build_prompt_render_context(
        request,
        template_set=template_set,
        mode=mode,
        examples=examples,
        estimation_user_message=estimation_user_message,
        preprocessing=preprocessing,
        inline_cleaning_block=inline_block,
        schema_version=schema_version,
        use_preprocessed_user_message=bool(use_preprocessed),
        renderer=renderer,
    )
    return renderer.render(template_set, context, examples_version=examples_version)
