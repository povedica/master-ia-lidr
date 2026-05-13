"""Domain model for structured estimation output (LLM JSON contract)."""

from __future__ import annotations

from typing import Any

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
    """Roll-up totals; when line items exist, the server aligns totals to their sums."""


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

    @model_validator(mode="before")
    @classmethod
    def align_totals_to_line_items(cls, data: Any) -> Any:
        """When line items exist, overwrite totals with their sums (LLM roll-ups often drift)."""

        if not isinstance(data, dict):
            return data
        sums = _sum_hours_and_cost_from_phases_and_line_items(
            data.get("phases"),
            data.get("line_items"),
        )
        if sums is None:
            return data
        sum_h, sum_c = sums
        out = dict(data)
        totals_val = out.get("totals")
        if isinstance(totals_val, dict):
            out["totals"] = {**totals_val, "hours": sum_h, "cost_eur": sum_c}
        else:
            out["totals"] = {"hours": sum_h, "cost_eur": sum_c}
        return out

    @field_validator("assumptions", "risks")
    @classmethod
    def non_empty_strings(cls, v: list[str]) -> list[str]:
        for s in v:
            if not s.strip():
                raise ValueError("list items must be non-empty strings")
        return v


def _sum_hours_and_cost_from_phases_and_line_items(
    phases: object,
    line_items: object,
) -> tuple[float, float] | None:
    """Return (sum_hours, sum_cost) when at least one line item exists; else None."""

    sum_h = 0.0
    sum_c = 0.0
    count = 0
    if isinstance(phases, list):
        for ph in phases:
            items: object
            if isinstance(ph, EstimationPhase):
                items = ph.items
            elif isinstance(ph, dict):
                items = ph.get("items") or []
            else:
                continue
            if not isinstance(items, list):
                continue
            for li in items:
                if isinstance(li, EstimationLineItem):
                    sum_h += li.hours
                    sum_c += li.cost_eur
                    count += 1
                elif isinstance(li, dict):
                    sum_h += float(li.get("hours", 0) or 0)
                    sum_c += float(li.get("cost_eur", 0) or 0)
                    count += 1
    if isinstance(line_items, list):
        for li in line_items:
            if isinstance(li, EstimationLineItem):
                sum_h += li.hours
                sum_c += li.cost_eur
                count += 1
            elif isinstance(li, dict):
                sum_h += float(li.get("hours", 0) or 0)
                sum_c += float(li.get("cost_eur", 0) or 0)
                count += 1
    if count == 0:
        return None
    return sum_h, sum_c
