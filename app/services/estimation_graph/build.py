"""Graph wiring helpers for the Session 13 estimation graph (feature-066).

``build_graph`` (full agent wiring) lands in a later baby step. This module owns
the pure routing helpers that the compiled graph will call.
"""

from __future__ import annotations

from langgraph.types import Send

from app.config import get_settings
from app.services.estimation_graph.state import EstimationState


def fan_out_hours(state: EstimationState):
    """Conditional edge after gate 1: one ``Send`` per approved task."""
    modules = state.get("approved_modules") or []
    sends = [
        Send(
            "estimate_task_hours",
            {
                "module": module["name"],
                "task": task["name"],
                "description": task.get("description"),
            },
        )
        for module in modules
        for task in (module.get("tasks") or [])
        if task.get("name")
    ]
    return sends or "recover_and_handover"


def route_after_gate2(state: EstimationState) -> str:
    """Conditional edge after gate 2: draft a proposal, or end."""
    settings = get_settings()
    decision = state.get("gate2_decision") or {}
    if settings.graph_proposal_enabled and decision.get("want_proposal"):
        return "proposal"
    return "end"
