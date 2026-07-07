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


class HallucinationJudgeLineResult(BaseModel):
    """One line verdict returned by the batched hallucination judge."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(..., ge=0)
    grade: HallucinationLineGrade


class HallucinationJudgeBatchResult(BaseModel):
    """Structured LLM output for batched line-vs-anchor judging."""

    model_config = ConfigDict(extra="forbid")

    lines: list[HallucinationJudgeLineResult] = Field(default_factory=list)


class HallucinationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    lines: list[HallucinationLineReport]
    counts: dict[HallucinationLineGrade, int]
    has_degraded: bool
