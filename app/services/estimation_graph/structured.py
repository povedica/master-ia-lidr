"""Structured LLM helper for graph agents (monkeypatch seam for tests)."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from app.config import Settings
from app.services.llm_chain import build_provider_chain
from app.services.provider_routing import resolve_first_litellm_route
from app.services.structured_llm_client import complete_structured

TModel = TypeVar("TModel", bound=BaseModel)


async def complete_graph_structured(
    *,
    system_prompt: str,
    user_prompt: str,
    response_model: type[TModel],
    model: str,
    settings: Settings,
) -> TModel:
    """Run a structured completion via LiteLLM + Instructor.

    ``model`` is the graph-specific override (e.g. ``graph_classifier_model``).
    Tests monkeypatch this function at module level.
    """
    route = resolve_first_litellm_route(build_provider_chain(settings))
    if route is None:
        raise RuntimeError(
            "Graph structured LLM requires a live LiteLLM provider "
            "(configure OpenAI or Anthropic)."
        )
    litellm_model = model.strip() or route.litellm_model
    result, _usage, _finish = await complete_structured(
        litellm_model=litellm_model,
        chain_provider=route.provider_name,
        api_key=route.api_key,
        timeout_seconds=route.timeout_seconds,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_output_tokens=settings.estimation_output_tokens_max,
        response_model=response_model,
        max_attempts=settings.structured_output_max_attempts,
    )
    return result
