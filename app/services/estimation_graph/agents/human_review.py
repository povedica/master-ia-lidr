"""``human_review`` — conditional HITL interrupt node (feature-067).

Discipline: call ``interrupt()`` before writing reducer-backed channels. On resume
LangGraph re-executes the node from the top.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.types import interrupt
from pydantic import ValidationError

from app.schemas.graph_estimation import parse_human_resolution
from app.services.estimation_graph.state import EstimationState

logger = logging.getLogger(__name__)


async def human_review(state: EstimationState) -> dict[str, Any]:
    """Pause for estimation review; fold a typed human resolution on resume."""
    validation = state.get("validation") or {}
    payload = {
        "gate": "estimation_review",
        "estimation_id": state.get("estimation_id"),
        "status": "awaiting_human_review",
        "estimate": state.get("estimate"),
        "validation": validation,
        "confidence": state.get("confidence"),
        "review_reasons": list(validation.get("review_reasons") or []),
    }
    decision = interrupt(payload)
    if not isinstance(decision, dict):
        raise ValueError("human_review resume payload must be an object")
    try:
        resolution = parse_human_resolution(decision)
    except ValidationError as exc:
        raise ValueError(f"invalid human resolution: {exc.error_count()} error(s)") from exc

    update: dict[str, Any] = {
        "human_review": {
            "gate": payload["gate"],
            "estimation_id": payload["estimation_id"],
            "review_reasons": payload["review_reasons"],
        },
        "human_resolution": resolution.model_dump(),
    }
    if resolution.action == "adjust":
        update["estimate"] = resolution.adjusted_estimate
        update["human_adjustment_validated"] = False
    logger.info(
        "graph_human_review_resumed",
        extra={"action": resolution.action, "gate": "estimation_review"},
    )
    return update
