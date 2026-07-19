"""``classifier_agent`` — complexity + reformulation, then handover to structure."""

from __future__ import annotations

import logging

from langgraph.types import Command

from app.config import get_settings
from app.services.estimation_graph import structured as graph_structured
from app.services.estimation_graph.personas import persona_for
from app.services.estimation_graph.schemas import ComplexityClassification

logger = logging.getLogger(__name__)

_CLASSIFIER_SYSTEM_PROMPT = (
    "You are an estimation triage analyst. You are given a raw, messy client meeting "
    "transcript (any language). Do TWO things:\n"
    "1. Judge the COMPLEXITY of the estimation this project will require: 'low' (a "
    "single simple component), 'medium' (a few related components) or 'high' (many "
    "disparate components and/or third-party integrations).\n"
    "2. REFORMULATE the transcript into a clean, self-contained project brief in "
    "concise technical English: the components the client wants, their scope and "
    "constraints, with small talk, anecdotes and digressions removed. Never invent "
    "scope the transcript gives no evidence for.\n"
    "Return the complexity, the reformulated brief and one line on why."
)


async def classifier_agent(state: dict) -> Command:
    """Transcript → (complexity, reformulated brief) → handover to structure_agent."""
    settings = get_settings()
    persona = persona_for("classifier_agent", enabled=settings.graph_personas_enabled)
    system_prompt = (
        f"{persona}\n\n{_CLASSIFIER_SYSTEM_PROMPT}" if persona else _CLASSIFIER_SYSTEM_PROMPT
    )
    result = await graph_structured.complete_graph_structured(
        system_prompt=system_prompt,
        user_prompt=state["transcript"],
        response_model=ComplexityClassification,
        model=settings.graph_classifier_model,
        settings=settings,
    )
    logger.info(
        "agent_classifier_done",
        extra={
            "complexity": result.complexity,
            "brief_chars": len(result.reformulated_transcript),
        },
    )
    return Command(
        goto="structure_agent",
        update={
            "complexity": result.complexity,
            "reformulated_transcript": result.reformulated_transcript,
        },
    )
