"""Pydantic models for golden session evaluation cases."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class GoldenCategory(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    AMBIGUOUS = "ambiguous"
    CONTRADICTION = "contradiction"
    MULTILINGUAL = "multilingual"


class HardConstraints(BaseModel):
    must_not_mention: list[str] = Field(default_factory=list)
    min_line_items: int | None = Field(default=None, ge=1)


class ExpectedMetadataSignals(BaseModel):
    project_name: str | None = None
    project_type: str | None = None
    target_audience: str | None = None
    mentioned_technologies_contains: list[str] = Field(default_factory=list)
    detected_constraints_contains: list[str] = Field(default_factory=list)


class SuccessCriteria(BaseModel):
    expected_hours_range: tuple[float, float] | None = None
    expected_components: list[str] = Field(default_factory=list)
    expected_risks: list[str] = Field(default_factory=list)
    expected_metadata_signals: ExpectedMetadataSignals | None = None
    expected_confidence_band: tuple[float, float] | None = None
    hard_constraints: HardConstraints = Field(default_factory=HardConstraints)

    @field_validator("expected_hours_range", "expected_confidence_band", mode="before")
    @classmethod
    def coerce_pair(cls, value: Any) -> tuple[float, float] | None:
        if value is None:
            return None
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return float(value[0]), float(value[1])
        raise ValueError("expected range must be a two-element list")


class GoldenTurnSubmit(BaseModel):
    project_name: str | None = None
    one_line_summary: str | None = None
    project_type: str | None = None
    target_audience: str | None = None
    industry: str | None = None
    transcript: str = Field(..., min_length=80)
    additional_extra_info: str | None = None


class GoldenTurn(BaseModel):
    label: str = Field(..., min_length=1)
    submit: GoldenTurnSubmit
    expect_status: int = 200
    skip_estimate: bool = False


class GoldenSessionCase(BaseModel):
    case_id: str = Field(..., min_length=3, pattern=r"^[a-z0-9-]+$")
    category: GoldenCategory
    description: str = Field(..., min_length=10)
    turns: list[GoldenTurn] = Field(..., min_length=1)
    eval_turn_index: int = Field(..., ge=0)
    expected_metadata_signals: ExpectedMetadataSignals = Field(default_factory=ExpectedMetadataSignals)
    success_criteria: SuccessCriteria = Field(default_factory=SuccessCriteria)
    notes_for_judge: str = Field(default="")

    @field_validator("eval_turn_index")
    @classmethod
    def eval_turn_within_bounds(cls, value: int, info: Any) -> int:
        turns = info.data.get("turns")
        if turns is not None and value >= len(turns):
            raise ValueError("eval_turn_index must be less than len(turns)")
        return value
