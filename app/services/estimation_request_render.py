"""Thin delegates to versioned Jinja2 prompt rendering."""

from __future__ import annotations

from typing import Final

from app.config import Settings
from app.schemas.estimation_request import EstimationRequest
from app.services.estimation_prompt_rendering import (
    render_assessment_surface as _render_assessment_surface,
    render_guided_user_message as _render_guided_user_message,
)

USER_MESSAGE_TEMPLATE_VERSION: Final[str] = "guided-form-v2"


def render_estimation_assessment_surface(
    request: EstimationRequest,
    *,
    version: str | None = None,
    settings: Settings | None = None,
) -> str:
    """Narrow text for domain guardrail + adaptive mode selection."""

    return _render_assessment_surface(request, version=version, settings=settings)


def render_estimation_user_message(
    request: EstimationRequest,
    *,
    version: str | None = None,
    settings: Settings | None = None,
) -> str:
    """Build the full guided-form user message (Markdown, deterministic layout)."""

    return _render_guided_user_message(request, version=version, settings=settings)


def user_message_template_version() -> str:
    """Version label for logs and documentation."""

    return USER_MESSAGE_TEMPLATE_VERSION
