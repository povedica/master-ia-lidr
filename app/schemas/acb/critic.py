"""Critic role structured feedback schemas."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CriticIssueCategory(StrEnum):
    missing_component = "missing_component"
    arithmetic_inconsistency = "arithmetic_inconsistency"
    metadata_inconsistency = "metadata_inconsistency"
    risk_gap = "risk_gap"
    scope_mismatch = "scope_mismatch"
    justification_breakdown_mismatch = "justification_breakdown_mismatch"
    confidence_mismatch = "confidence_mismatch"
    other = "other"


class CriticIssueSeverity(StrEnum):
    critical = "critical"
    major = "major"
    minor = "minor"


class CriticIssue(BaseModel):
    """One material defect detected in an Actor candidate."""

    model_config = ConfigDict(extra="forbid")

    category: CriticIssueCategory
    severity: CriticIssueSeverity
    message: str = Field(..., min_length=1, max_length=500)
    affected_area: str = Field(..., min_length=1, max_length=120)
    suggested_fix: str = Field(..., min_length=1, max_length=500)
    evidence: str | None = Field(default=None, max_length=500)


class CriticFeedback(BaseModel):
    """Structured Critic output; must not contain a replacement estimate."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., min_length=1, max_length=16)
    overall_assessment: Literal["pass", "fail"]
    issues: list[CriticIssue]
    summary: str = Field(..., min_length=1, max_length=500)
