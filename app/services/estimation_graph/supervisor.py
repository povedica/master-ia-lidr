"""Hand-written supervisor for the Session 14 estimation graph (feature-067).

No business tools. Every forward transition is an explicit
``Command(goto=..., update=...)``.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END
from langgraph.types import Command

from app.config import get_settings
from app.services.estimation_graph.review_policy import (
    ReviewSignals,
    requires_human_review,
)
from app.services.estimation_graph.state import EstimationState

logger = logging.getLogger(__name__)

WORKER_REQUIREMENTS = "requirements_extractor"
WORKER_BUDGET = "budget_searcher"
WORKER_ESTIMATE = "estimate_generator"
WORKER_VALIDATOR = "coherence_validator"
NODE_HUMAN_REVIEW = "human_review"


def _has_requirements(state: EstimationState) -> bool:
    requirements = state.get("requirements")
    return bool(requirements)


def _decision(
    *,
    goto: str | object,
    reason: str,
    extra: dict[str, Any] | None = None,
) -> Command:
    target = goto if isinstance(goto, str) else "END"
    update: dict[str, Any] = {
        "last_route": target,
        "route_reason": reason,
        "supervisor_decisions": [{"goto": target, "reason": reason}],
    }
    if extra:
        update.update(extra)
    logger.info(
        "graph_supervisor_route",
        extra={"goto": target, "route_reason": reason},
    )
    return Command(goto=goto, update=update)


def _signals_from_state(state: EstimationState) -> ReviewSignals:
    validation = state.get("validation") or {}
    confidence = state.get("confidence")
    if confidence is None:
        confidence = 0.0
    return ReviewSignals(
        confidence=float(confidence),
        out_of_historical_range=bool(validation.get("out_of_historical_range")),
        no_precedent=bool(validation.get("no_precedent")),
    )


def supervisor(
    state: EstimationState,
    *,
    confidence_threshold: float | None = None,
) -> Command:
    """Inspect shared state and return the next ``Command`` transition."""
    threshold = (
        confidence_threshold
        if confidence_threshold is not None
        else get_settings().graph_human_review_confidence_threshold
    )

    resolution = state.get("human_resolution")
    if isinstance(resolution, dict):
        action = resolution.get("action")
        if action == "reject":
            return _decision(
                goto=END,
                reason="human_rejected",
                extra={"status": "rejected"},
            )
        if action == "approve":
            return _decision(
                goto=END,
                reason="human_approved",
                extra={"status": "completed"},
            )
        if action == "adjust":
            if state.get("human_adjustment_validated"):
                return _decision(
                    goto=END,
                    reason="human_adjusted_finalized",
                    extra={"status": "completed"},
                )
            adjusted = resolution.get("adjusted_estimate")
            extra: dict[str, Any] = {"human_adjustment_validated": False}
            if isinstance(adjusted, dict):
                extra["estimate"] = adjusted
                # Force a fresh validation pass after the fold.
                extra["validation"] = None
            return _decision(
                goto=WORKER_VALIDATOR,
                reason="human_adjusted_revalidate",
                extra=extra,
            )

    if not _has_requirements(state):
        return _decision(goto=WORKER_REQUIREMENTS, reason="missing_requirements")

    if not state.get("search_attempted"):
        return _decision(goto=WORKER_BUDGET, reason="historical_search_pending")

    if not state.get("estimate"):
        return _decision(goto=WORKER_ESTIMATE, reason="estimation_pending")

    if state.get("validation") is None:
        return _decision(goto=WORKER_VALIDATOR, reason="validation_pending")

    signals = _signals_from_state(state)
    if requires_human_review(signals, threshold=threshold):
        return _decision(
            goto=NODE_HUMAN_REVIEW,
            reason="human_review_required",
            extra={"status": "awaiting_human_review"},
        )

    return _decision(
        goto=END,
        reason="validation_passed",
        extra={"status": "completed"},
    )
