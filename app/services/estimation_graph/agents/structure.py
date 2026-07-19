"""``structure_agent`` — module → task breakdown via Session 12 ``run_structure_agent``."""

from __future__ import annotations

import json
import logging

from app.config import get_settings
from app.services.agentic.agent_loop import run_structure_agent
from app.services.agentic.openai_client import get_async_openai_client
from app.services.estimation_graph.personas import persona_for

logger = logging.getLogger(__name__)


def _effort_for_complexity(complexity: str | None) -> str:
    """Map the classifier's complexity to a Responses reasoning effort."""
    settings = get_settings()
    try:
        mapping = json.loads(settings.graph_structure_effort_by_complexity)
    except json.JSONDecodeError:
        mapping = {}
    if not isinstance(mapping, dict):
        mapping = {}
    return str(mapping.get(complexity or "medium", settings.agent_reasoning_effort))


async def structure_agent(state: dict) -> dict:
    """Reformulated brief → module→task structure (reuses the S12 structure agent)."""
    settings = get_settings()
    client = get_async_openai_client(settings)
    if client is None:
        raise RuntimeError("Async OpenAI client is not available (no OpenAI key).")

    brief = state.get("reformulated_transcript") or state.get("transcript") or ""
    effort = _effort_for_complexity(state.get("complexity"))
    structure, _trace = await run_structure_agent(
        brief,
        client=client,
        model=settings.agent_model,
        reasoning_effort=effort,
        persona=persona_for("structure_agent", enabled=settings.graph_personas_enabled),
    )
    task_count = sum(len(module.tasks) for module in structure.modules)
    logger.info(
        "agent_structure_node_done",
        extra={
            "modules": len(structure.modules),
            "tasks": task_count,
            "effort": effort,
        },
    )
    return {"structure": structure.model_dump()}
