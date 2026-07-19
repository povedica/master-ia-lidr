"""Human gates (HITL) — ``interrupt()`` / ``Command(resume=...)``.

Critical discipline: call ``interrupt()`` FIRST and only write last-write-wins
fields afterwards. Never write a reducer channel before interrupting — on resume
LangGraph re-executes the node from the top.
"""

from __future__ import annotations

import logging

from langgraph.types import interrupt

from app.services.estimation_graph.agents._common import (
    modules_from_structure,
    recompute_estimate_totals,
)

logger = logging.getLogger(__name__)


async def human_gate_structure(state: dict) -> dict:
    """HUMAN GATE 1 — review/edit the module→task breakdown, then approve.

    Resume decision shape::

        {"approved": bool, "modules": [ {"name": ..., "tasks": [{"name", "description"}]} ]}
    """
    decision = interrupt(
        {
            "gate": "structure_review",
            "estimation_id": state.get("estimation_id"),
            "complexity": state.get("complexity"),
            "structure": state.get("structure"),
        }
    )
    decision = decision or {}
    modules = decision.get("modules") or modules_from_structure(state.get("structure"))
    logger.info(
        "human_gate_structure_resumed",
        extra={"approved": decision.get("approved"), "modules": len(modules)},
    )
    return {"approved_modules": modules, "gate1_decision": decision}


async def human_gate_analysis(state: dict) -> dict:
    """HUMAN GATE 2 — final review: validate, complete missing data, decide.

    Resume decision shape::

        {"validated": bool, "estimate_overrides": {...}, "want_proposal": bool}
    """
    decision = interrupt(
        {
            "gate": "final_review",
            "estimation_id": state.get("estimation_id"),
            "estimate": state.get("estimate"),
            "analysis_report": state.get("analysis_report"),
        }
    )
    decision = decision or {}
    overrides = decision.get("estimate_overrides") or {}
    estimate = {**(state.get("estimate") or {}), **overrides}
    if estimate.get("modules"):
        estimate = {**estimate, **recompute_estimate_totals(estimate["modules"])}
    status = "validated" if decision.get("validated") else "needs_review"
    logger.info(
        "human_gate_analysis_resumed",
        extra={
            "validated": decision.get("validated"),
            "want_proposal": decision.get("want_proposal"),
            "overrides": len(overrides),
        },
    )
    return {"estimate": estimate, "gate2_decision": decision, "status": status}
