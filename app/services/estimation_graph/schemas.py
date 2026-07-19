"""Node-internal LLM I/O models for the Session 13 estimation graph.

These are the ``response_model``s structured-output nodes hand to
``complete_structured``. Public HTTP contracts live in
``app/schemas/graph_estimation.py`` (later step).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Complexity = Literal["low", "medium", "high"]


class ExtractedRequirement(BaseModel):
    """One structured requirement emitted by ``requirements_extractor``."""

    id: str = Field(min_length=1, description="Stable requirement identifier.")
    text: str = Field(min_length=1, description="Requirement statement.")
    category: str = Field(
        default="general",
        description="Coarse category (e.g. backend, frontend, integration).",
    )


class ExtractedRequirements(BaseModel):
    """Structured extraction output for the requirements worker."""

    requirements: list[ExtractedRequirement] = Field(default_factory=list)


class ComplexityClassification(BaseModel):
    """Output of ``classifier_agent``: complexity + a reformulated brief."""

    complexity: Complexity = Field(
        description=(
            "How complex the estimation is. 'low' = one simple component; "
            "'medium' = a few components; 'high' = many disparate components / integrations."
        )
    )
    reformulated_transcript: str = Field(
        min_length=1,
        description=(
            "The transcript rewritten as a clean, self-contained project "
            "brief in technical English. No invented scope."
        ),
    )
    reasoning: str = Field(description="One line on why that complexity was assigned.")


class WeakPoint(BaseModel):
    """One weakness the analysis agent flags for the human's final review."""

    area: str = Field(description="Module/task or cross-cutting concern.")
    issue: str = Field(description="What is uncertain, ungrounded or contradictory.")
    severity: Literal["low", "medium", "high"] = "medium"


class ReliabilityReport(BaseModel):
    """Output of ``analysis_agent``: a data-reliability read of the estimate."""

    overall_confidence: Literal["low", "medium", "high"] = Field(
        description="Overall confidence in the estimate as a whole."
    )
    grounded_task_ratio: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of tasks that got hours from a historical match (0..1).",
    )
    weak_points: list[WeakPoint] = Field(
        default_factory=list,
        description="Soft spots the human should check or complete.",
    )
    summary: str = Field(description="Short prose read of the estimate's reliability.")


class CommercialProposal(BaseModel):
    """Output of ``proposal_agent`` (bonus): a client-facing commercial proposal."""

    title: str = Field(description="Proposal title, e.g. the project name.")
    executive_summary: str = Field(description="2-4 sentences for a client executive.")
    scope: list[str] = Field(
        default_factory=list,
        description="Bullet scope: the modules/deliverables included.",
    )
    total_engineer_days: int | None = Field(
        default=None,
        ge=0,
        description="Headline effort, echoed from the validated estimate.",
    )
    body_markdown: str = Field(
        description="Full proposal as Markdown, grounded ONLY in the validated estimate."
    )
