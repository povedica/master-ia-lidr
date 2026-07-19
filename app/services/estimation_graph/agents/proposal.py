"""``proposal_agent`` (bonus) — commercial proposal from a validated estimate."""

from __future__ import annotations

import logging

from app.config import get_settings
from app.services.estimation_graph import structured as graph_structured
from app.services.estimation_graph.personas import persona_for
from app.services.estimation_graph.schemas import CommercialProposal

logger = logging.getLogger(__name__)

_PROPOSAL_SYSTEM_PROMPT = (
    "You are a delivery lead writing a concise commercial proposal for a client, based "
    "STRICTLY on a validated software estimate (modules → tasks with engineer-days) and "
    "its reliability report. Write a title, a 2-4 sentence executive summary, a bullet "
    "scope of the modules/deliverables, echo the total engineer-days, and a full "
    "proposal body in Markdown. Do NOT invent scope, prices or numbers not present in "
    "the estimate. Keep it honest and client-ready."
)


def _proposal_input(estimate: dict, analysis_report: dict) -> str:
    lines = [
        f"total_engineer_days: {estimate.get('total_engineer_days')}",
        f"confidence: {estimate.get('confidence')}",
        f"reliability_summary: {(analysis_report or {}).get('summary', '')}",
        "modules:",
    ]
    for module in estimate.get("modules") or []:
        task_hours = [
            task.get("estimated_hours")
            for task in (module.get("tasks") or [])
            if task.get("estimated_hours") is not None
        ]
        lines.append(
            f"  - {module.get('name')}: {len(module.get('tasks') or [])} tasks, "
            f"{sum(task_hours)}h total"
        )
    return "\n".join(lines)


async def build_proposal(
    estimate: dict,
    analysis_report: dict,
    *,
    persona: str | None = None,
) -> CommercialProposal:
    """Draft a ``CommercialProposal`` (graph node + future on-demand HTTP)."""
    settings = get_settings()
    system_prompt = (
        f"{persona}\n\n{_PROPOSAL_SYSTEM_PROMPT}" if persona else _PROPOSAL_SYSTEM_PROMPT
    )
    user_message = _proposal_input(estimate or {}, analysis_report or {})
    return await graph_structured.complete_graph_structured(
        system_prompt=system_prompt,
        user_prompt=user_message,
        response_model=CommercialProposal,
        model=settings.graph_proposal_model,
        settings=settings,
    )


async def proposal_agent(state: dict) -> dict:
    """Validated estimate → commercial proposal (Markdown)."""
    persona = persona_for(
        "proposal_agent",
        enabled=get_settings().graph_personas_enabled,
    )
    proposal = await build_proposal(
        state.get("estimate") or {},
        state.get("analysis_report") or {},
        persona=persona,
    )
    logger.info(
        "agent_proposal_done",
        extra={"title": proposal.title, "scope": len(proposal.scope)},
    )
    return {"proposal": proposal.body_markdown}
