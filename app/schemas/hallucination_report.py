"""Hallucination audit report models for RAG estimation."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class HallucinationLineGrade(StrEnum):
    GROUNDED = "grounded"
    DEGRADED = "degraded"
    INSUFFICIENT = "insufficient"


class HallucinationLineReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(..., ge=0)
    component: str
    grade: HallucinationLineGrade
    anchor_max: float | None = None


class HallucinationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    lines: list[HallucinationLineReport]
    counts: dict[HallucinationLineGrade, int]
    has_degraded: bool
