"""Hour range surfaced when historical task neighbours disagree (FR-22)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HourRange(BaseModel):
    """Honest uncertainty band alongside a point estimate."""

    low: int = Field(..., ge=0)
    high: int = Field(..., ge=0)
    reason: str = Field(..., min_length=1)
