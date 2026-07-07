"""Coherence audit report models for RAG estimation."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class CoherenceLineStatus(StrEnum):
    COHERENT_OK = "coherent_ok"
    TOTAL_HOURS_MISMATCH = "total_hours_mismatch"
    DUPLICATE_COMPONENT = "duplicate_component"
    INSUFFICIENT_CONTEXT_VIOLATION = "insufficient_context_violation"
    ZERO_HOURS_GROUNDED = "zero_hours_grounded"


class CoherenceLineReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(..., ge=-1)
    component: str
    status: CoherenceLineStatus


class CoherenceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    lines: list[CoherenceLineReport]
    counts: dict[CoherenceLineStatus, int]
    has_violations: bool
