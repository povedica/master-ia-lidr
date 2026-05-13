"""Domain model for structured estimation output (LLM JSON contract)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MoneyAndHours(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hours: float = Field(..., ge=0)
    cost_eur: float = Field(..., ge=0)


class EstimationLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=80)
    hours: float = Field(..., ge=0)
    cost_eur: float = Field(..., ge=0)


class EstimationPhase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    items: list[EstimationLineItem] = Field(default_factory=list)


class EstimationTotals(MoneyAndHours):
    """Roll-up totals; validators may cross-check sum(items)."""


class EstimationResult(BaseModel):
    """Single source of truth for structured estimation output (API + LLM contract)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1", max_length=16)
    title: str = Field(..., min_length=3, max_length=200)
    summary: str = Field(..., min_length=20, max_length=2000)
    phases: list[EstimationPhase] = Field(default_factory=list)
    line_items: list[EstimationLineItem] = Field(default_factory=list)
    totals: EstimationTotals
    duration_weeks: float = Field(..., gt=0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    risks: list[str] = Field(default_factory=list, max_length=20)
    recommended_team: list[str] = Field(default_factory=list, max_length=15)
    human_summary: str | None = Field(
        default=None,
        max_length=4000,
        description="Optional narrative; not the primary machine-readable payload.",
    )
    presentation: dict[str, str] | None = Field(
        default=None,
        description="Optional UI hints; same top-level schema for all output_format values.",
    )

    @model_validator(mode="after")
    def coherent_totals(self) -> EstimationResult:
        flat = [li for ph in self.phases for li in ph.items] + self.line_items
        if not flat:
            return self
        sum_hours = sum(x.hours for x in flat)
        sum_cost = sum(x.cost_eur for x in flat)
        if abs(sum_hours - self.totals.hours) > 0.51:
            raise ValueError("totals.hours must match sum of line items (within tolerance)")
        if abs(sum_cost - self.totals.cost_eur) > 1.0:
            raise ValueError("totals.cost_eur must match sum of line items (within tolerance)")
        return self

    @field_validator("assumptions", "risks")
    @classmethod
    def non_empty_strings(cls, v: list[str]) -> list[str]:
        for s in v:
            if not s.strip():
                raise ValueError("list items must be non-empty strings")
        return v
