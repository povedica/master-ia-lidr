"""Render grounded RAG estimation prompts (English, rag/v1)."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.prompt_renderer import PromptRenderer

_RAG_PROMPT_VERSION = "estimation/rag/v1"
_SYSTEM_TEMPLATE = "estimation/rag/v1/system.j2"
_USER_TEMPLATE = "estimation/rag/v1/user.j2"
_CITATION_INSTRUCTIONS = "estimation/rag/v1/partials/citation_instructions.md.j2"
_STRUCTURED_OUTPUT_HINT = "estimation/rag/v1/partials/structured_output_hint.md.j2"


@dataclass(frozen=True)
class RenderedRagPrompt:
    system_prompt: str
    user_prompt: str
    prompt_version: str


def render_rag_estimation_prompt(
    *,
    question: str,
    prompt_block: str,
) -> RenderedRagPrompt:
    """Render RAG system and user prompts with assembled retrieval context."""

    renderer = PromptRenderer()
    partial_ctx = {
        "citation_instructions_template": _CITATION_INSTRUCTIONS,
        "structured_output_hint_template": _STRUCTURED_OUTPUT_HINT,
    }
    system_prompt = renderer.render_partial(_SYSTEM_TEMPLATE, partial_ctx)
    user_prompt = renderer.render_partial(
        _USER_TEMPLATE,
        {"question": question.strip(), "prompt_block": prompt_block},
    )
    return RenderedRagPrompt(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        prompt_version=_RAG_PROMPT_VERSION,
    )
