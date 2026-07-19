"""``requirements_extractor`` — model-only structured requirements worker."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.config import Settings, get_settings
from app.services.estimation_graph import structured as graph_structured
from app.services.estimation_graph.schemas import ExtractedRequirements
from app.services.estimation_graph.state import EstimationState

logger = logging.getLogger(__name__)

CompleteFn = Callable[..., Awaitable[ExtractedRequirements]]

_SYSTEM_PROMPT = (
    "You extract structured software-estimation requirements from a client "
    "meeting transcript. Return a concise list of distinct requirements with "
    "stable ids (req-1, req-2, …), short text, and a coarse category. Do not "
    "invent scope the transcript does not support. Do not estimate hours."
)


def build_requirements_extractor(
    *,
    complete_fn: CompleteFn | None = None,
) -> Callable[[EstimationState], Awaitable[dict[str, Any]]]:
    """Build a model-only worker (no business-tool registry)."""

    async def requirements_extractor(state: EstimationState) -> dict[str, Any]:
        settings = get_settings()
        transcript = (state.get("transcript") or "").strip()
        complete = complete_fn or _default_complete
        try:
            result = await complete(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=transcript,
                response_model=ExtractedRequirements,
                model=settings.graph_extraction_model,
                settings=settings,
            )
        except Exception as exc:  # noqa: BLE001 — convert at worker boundary
            logger.warning(
                "graph_requirements_extractor_failed",
                extra={"error_type": type(exc).__name__},
            )
            return {
                "errors": [f"requirements_extractor failed: {type(exc).__name__}"],
                "completed_workers": ["requirements_extractor"],
                "agent_contributions": [
                    {
                        "worker": "requirements_extractor",
                        "summary": "extraction failed",
                    }
                ],
            }

        requirements = [
            {"id": item.id, "text": item.text, "category": item.category}
            for item in result.requirements
        ]
        if not requirements:
            return {
                "errors": ["requirements_extractor returned no requirements"],
                "completed_workers": ["requirements_extractor"],
                "agent_contributions": [
                    {
                        "worker": "requirements_extractor",
                        "summary": "empty extraction",
                    }
                ],
            }

        logger.info(
            "graph_requirements_extractor_done",
            extra={"requirement_count": len(requirements)},
        )
        return {
            "requirements": requirements,
            "completed_workers": ["requirements_extractor"],
            "agent_contributions": [
                {
                    "worker": "requirements_extractor",
                    "summary": f"{len(requirements)} requirements extracted",
                }
            ],
        }

    return requirements_extractor


async def _default_complete(
    *,
    system_prompt: str,
    user_prompt: str,
    response_model: type[ExtractedRequirements],
    model: str,
    settings: Settings,
) -> ExtractedRequirements:
    return await graph_structured.complete_graph_structured(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_model=response_model,
        model=model,
        settings=settings,
    )
