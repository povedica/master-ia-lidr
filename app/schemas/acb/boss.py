"""Boss role governance decision schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class BossAction(StrEnum):
    accept = "accept"
    revise = "revise"
    synthesize = "synthesize"


class BossDecision(BaseModel):
    """Process governance decision for one ACB iteration."""

    model_config = ConfigDict(extra="forbid")

    action: BossAction
    reasoning: str = Field(..., min_length=1, max_length=800)
    revision_instructions: str | None = Field(default=None, max_length=2000)
    confidence_in_decision: float = Field(..., ge=0.0, le=1.0)
