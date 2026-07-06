"""Citation audit report models for RAG estimation."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class CitationLineStatus(StrEnum):
    GROUNDED_OK = "grounded_ok"
    DANGLING_CITATION = "dangling_citation"
    INSUFFICIENT_DATA = "insufficient_data"
    INTEGRITY_VIOLATION = "integrity_violation"


class CitationLineReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(..., ge=0)
    component: str
    status: CitationLineStatus
    invalid_chunk_ids: list[int] = Field(default_factory=list)


class CitationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    lines: list[CitationLineReport]
    counts: dict[CitationLineStatus, int]
    has_dangling: bool
    has_integrity_violation: bool
