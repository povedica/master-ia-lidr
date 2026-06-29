"""Domain model for grounded RAG estimation output (LLM JSON contract)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SourceReference(BaseModel):
    """Chunk-level citation with literal evidence span."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: int = Field(..., ge=1)
    document_id: int = Field(..., ge=1)
    budget_id: str | None = Field(default=None, max_length=80)
    evidence: str = Field(..., min_length=1, max_length=4000)

    @field_validator("evidence")
    @classmethod
    def evidence_not_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evidence must be non-whitespace")
        return value


class RagEstimationLineItem(BaseModel):
    """One grounded or insufficient estimation line with optional citations."""

    model_config = ConfigDict(extra="forbid")

    component: str = Field(..., min_length=1, max_length=200)
    hours: float = Field(..., ge=0)
    rationale: str = Field(..., min_length=1, max_length=2000)
    grounded: bool
    sources: list[SourceReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def grounded_sources_integrity(self) -> RagEstimationLineItem:
        if self.grounded:
            if not self.sources:
                raise ValueError("grounded=true requires at least one source")
        else:
            if self.sources:
                raise ValueError("grounded=false requires empty sources")
            if self.hours != 0:
                raise ValueError("grounded=false requires hours=0")
        return self


class RagEstimationResult(BaseModel):
    """Structured RAG estimation with per-line citations."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="rag-1", max_length=16)
    summary: str = Field(..., min_length=20, max_length=2000)
    line_items: list[RagEstimationLineItem] = Field(default_factory=list)
    total_hours: float = Field(..., ge=0)
    currency: str = Field(default="EUR", max_length=8)
    insufficient_context: bool = False

    @model_validator(mode="before")
    @classmethod
    def align_total_hours_to_line_items(cls, data: Any) -> Any:
        """Recompute total_hours from line items to prevent LLM roll-up drift."""

        if not isinstance(data, dict):
            return data
        line_items = data.get("line_items")
        if not isinstance(line_items, list) or not line_items:
            return data
        total = 0.0
        for item in line_items:
            if isinstance(item, RagEstimationLineItem):
                total += item.hours
            elif isinstance(item, dict):
                total += float(item.get("hours", 0) or 0)
        out = dict(data)
        out["total_hours"] = total
        return out
