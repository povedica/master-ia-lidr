"""Wire and compile the multi-agent estimation graph (feature-066 / Session 13).

Topology:

    START → classifier_agent
    classifier_agent      ──Command(goto)──▶  structure_agent      (HANDOVER 1)
    structure_agent       ──edge──▶           human_gate_structure (interrupt #1)
    human_gate_structure  ──Send fan-out──▶   estimate_task_hours × N
    estimate_task_hours   ──edge──▶           recover_and_handover (join)
    recover_and_handover  ──Command(goto)──▶  analysis_agent       (HANDOVER 2)
    analysis_agent        ──edge──▶           human_gate_analysis  (interrupt #2)
    human_gate_analysis   ──conditional──▶    proposal_agent | END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.config import get_settings
from app.services.estimation_graph.agents import (
    analysis_agent,
    classifier_agent,
    estimate_task_hours,
    human_gate_analysis,
    human_gate_structure,
    proposal_agent,
    recover_and_handover,
    structure_agent,
)
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


def build_graph(checkpointer=None):
    """Build and compile the multi-agent estimation graph.

    ``checkpointer`` persists state per ``thread_id`` (``AsyncPostgresSaver`` in
    the app, ``MemorySaver`` in tests). Required for interrupt/resume at human gates.
    """
    builder = StateGraph(EstimationState)

    builder.add_node("classifier_agent", classifier_agent)
    builder.add_node("structure_agent", structure_agent)
    builder.add_node("human_gate_structure", human_gate_structure)
    builder.add_node("estimate_task_hours", estimate_task_hours)
    builder.add_node("recover_and_handover", recover_and_handover)
    builder.add_node("analysis_agent", analysis_agent)
    builder.add_node("human_gate_analysis", human_gate_analysis)
    builder.add_node("proposal_agent", proposal_agent)

    builder.add_edge(START, "classifier_agent")
    # classifier_agent → structure_agent is a Command(goto) handover (no static edge).
    builder.add_edge("structure_agent", "human_gate_structure")
    builder.add_conditional_edges(
        "human_gate_structure",
        fan_out_hours,
        ["estimate_task_hours", "recover_and_handover"],
    )
    builder.add_edge("estimate_task_hours", "recover_and_handover")
    # recover_and_handover → analysis_agent is a Command(goto) handover (no static edge).
    builder.add_edge("analysis_agent", "human_gate_analysis")
    builder.add_conditional_edges(
        "human_gate_analysis",
        route_after_gate2,
        {"proposal": "proposal_agent", "end": END},
    )
    builder.add_edge("proposal_agent", END)

    return builder.compile(checkpointer=checkpointer)
