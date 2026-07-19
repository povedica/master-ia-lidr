"""Per-task hours fan-out + agentic recovery join (handover to analysis)."""

from __future__ import annotations

import logging

from langgraph.types import Command

from app.config import get_settings
from app.schemas.rag_task_hours import TaskHoursEstimateView
from app.services.agentic.agent_loop import run_task_hours_recovery_agent
from app.services.agentic.agent_schemas import AgentTaskRef
from app.services.agentic.openai_client import get_async_openai_client
from app.services.agentic.retrieval_adapter import load_stub_retrieval_backend
from app.services.estimation_graph.agents._common import build_estimate, flag_reason
from app.services.estimation_graph.personas import persona_for
from app.services.rag_task_hours import consensus_hours

logger = logging.getLogger(__name__)


async def estimate_one(
    module: str,
    name: str,
    description: str | None,
    *,
    top_k: int,
    distance_threshold: float,
) -> TaskHoursEstimateView:
    """Per-task hours lookup seam.

    Production CLI/HTTP will bind a real ``estimate_one_task`` backend. Tests and
    ``--stub`` runners monkeypatch this function.
    """
    raise RuntimeError(
        "estimate_one is not bound; wire graph task-hours deps or monkeypatch in tests"
    )


async def estimate_task_hours(state: dict) -> dict:
    """FAN-OUT BRANCH: derive hours for ONE task (the ``Send`` arg is the state)."""
    settings = get_settings()
    module = state["module"]
    task = state["task"]
    description = state.get("description")
    est = await estimate_one(
        module,
        task,
        description,
        top_k=settings.task_hours_top_k,
        distance_threshold=settings.task_hours_distance_threshold,
    )
    logger.info(
        "estimate_task_hours_branch",
        extra={
            "module": module,
            "task": task,
            "has_match": est.has_match,
            "hours": est.estimated_hours,
        },
    )
    return {"task_hours": [est.model_dump(mode="json")]}


async def recover_and_handover(state: dict) -> Command:
    """JOIN: agentic recovery of doubtful tasks, build estimate, hand over."""
    settings = get_settings()
    approved = state.get("approved_modules") or []
    task_hours = list(state.get("task_hours") or [])
    by_key = {(row.get("module"), row.get("task")): row for row in task_hours}
    descriptions = {
        (module.get("name"), task.get("name")): task.get("description")
        for module in approved
        for task in (module.get("tasks") or [])
    }

    flagged: list[AgentTaskRef] = []
    for row in task_hours:
        reason = flag_reason(row)
        if reason is None:
            continue
        flagged.append(
            AgentTaskRef(
                module=row.get("module") or "",
                task=row.get("task") or "",
                description=descriptions.get((row.get("module"), row.get("task"))),
                reason=reason,
            )
        )

    client = get_async_openai_client(settings)
    merged = task_hours
    recovered_count = 0
    if flagged and client is not None:
        logger.info(
            "agentic_recovery_start",
            extra={"flagged": len(flagged), "total": len(task_hours)},
        )
        run = await run_task_hours_recovery_agent(
            flagged,
            client=client,
            model=settings.agent_model,
            reasoning_effort=settings.agent_reasoning_effort,
            max_iterations=settings.agent_max_iterations,
            # Stub until HTTP/CLI lifespan binds a real retrieval backend.
            retrieval_backend=load_stub_retrieval_backend(),
            consensus_fn=consensus_hours,
            persona=persona_for(
                "recover_and_handover",
                enabled=settings.graph_personas_enabled,
            ),
        )
        recovered = {
            (derivation.module, derivation.task): derivation
            for derivation in run.derivations
            if derivation.has_match and derivation.estimated_hours is not None
        }
        recovered_count = len(recovered)
        merged_map = dict(by_key)
        for key, derivation in recovered.items():
            base = merged_map.get(key, {"module": key[0], "task": key[1]})
            merged_map[key] = {
                **base,
                "estimated_hours": derivation.estimated_hours,
                "reliability": derivation.reliability,
                "has_match": True,
                "hour_range": None,
                "hours_range": None,
            }
        merged = list(merged_map.values())

    estimate = build_estimate(approved, merged)
    logger.info(
        "recover_and_handover_done",
        extra={
            "flagged": len(flagged),
            "recovered": recovered_count,
            "total_engineer_days": estimate.get("total_engineer_days"),
        },
    )
    return Command(
        goto="analysis_agent",
        update={"estimate": estimate, "task_hours": merged},
    )
