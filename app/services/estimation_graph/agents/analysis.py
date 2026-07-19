"""``analysis_agent`` — reliability report for the human's final review."""

from __future__ import annotations

import logging

from app.config import get_settings
from app.services.estimation_graph import structured as graph_structured
from app.services.estimation_graph.personas import persona_for
from app.services.estimation_graph.schemas import ReliabilityReport

logger = logging.getLogger(__name__)

_ANALYSIS_SYSTEM_PROMPT = (
    "You are an estimation reviewer. You are given a structured software estimate: "
    "modules → tasks, each task with derived engineer-hours, a reliability score "
    "(0..1) and whether it matched a historical analog. Write a RELIABILITY REPORT for "
    "the human who will approve it:\n"
    "- overall_confidence: how much to trust the estimate as a whole.\n"
    "- grounded_task_ratio: the fraction of tasks with grounded hours (use the value "
    "given in the input; do not recompute).\n"
    "- weak_points: the specific soft spots the human must check or complete — tasks "
    "with no match, low reliability, or contradictory analogs. Be concrete.\n"
    "- summary: a short honest prose read. Never invent numbers; only judge the ones given."
)


def _grounded_ratio(estimate: dict) -> float:
    tasks = [task for module in estimate.get("modules") or [] for task in (module.get("tasks") or [])]
    if not tasks:
        return 0.0
    grounded = sum(1 for task in tasks if task.get("estimated_hours") is not None)
    return round(grounded / len(tasks), 3)


def _estimate_digest(estimate: dict, ratio: float) -> str:
    """Compact, LLM-readable digest of the estimate for the report call."""
    lines = [
        f"total_engineer_days: {estimate.get('total_engineer_days')}",
        f"total_engineer_hours: {estimate.get('total_engineer_hours')}",
        f"grounded_task_ratio: {ratio}",
        "tasks:",
    ]
    for module in estimate.get("modules") or []:
        for task in module.get("tasks") or []:
            hours = task.get("estimated_hours")
            hours_text = f"{hours}h" if hours is not None else "NO MATCH"
            lines.append(
                f"  - [{module.get('name')}] {task.get('name')}: {hours_text} "
                f"(reliability={task.get('reliability')}, has_match={task.get('has_match')})"
            )
    return "\n".join(lines)


async def analysis_agent(state: dict) -> dict:
    """Estimate → reliability report (structured LLM call)."""
    settings = get_settings()
    estimate = state.get("estimate") or {}
    ratio = _grounded_ratio(estimate)
    user_message = _estimate_digest(estimate, ratio)
    persona = persona_for("analysis_agent", enabled=settings.graph_personas_enabled)
    system_prompt = f"{persona}\n\n{_ANALYSIS_SYSTEM_PROMPT}" if persona else _ANALYSIS_SYSTEM_PROMPT
    report = await graph_structured.complete_graph_structured(
        system_prompt=system_prompt,
        user_prompt=user_message,
        response_model=ReliabilityReport,
        model=settings.graph_analysis_model,
        settings=settings,
    )
    report.grounded_task_ratio = ratio
    logger.info(
        "agent_analysis_done",
        extra={
            "overall_confidence": report.overall_confidence,
            "grounded_task_ratio": ratio,
            "weak_points": len(report.weak_points),
        },
    )
    return {"analysis_report": report.model_dump()}
