"""HTTP schemas for per-task hours estimation (feature-062)."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class TaskHoursTaskInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class TaskHoursModuleInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    tasks: list[TaskHoursTaskInput] = Field(min_length=1)

    @field_validator("tasks")
    @classmethod
    def tasks_not_empty(cls, value: list[TaskHoursTaskInput]) -> list[TaskHoursTaskInput]:
        if not value:
            raise ValueError("tasks must not be empty")
        return value


class TaskHoursRequest(BaseModel):
    modules: list[TaskHoursModuleInput] = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=50)
    distance_threshold: float | None = Field(default=None, ge=0.0, le=2.0)


class TaskNeighborView(BaseModel):
    chunk_id: int
    budget_id: str | None = None
    estimated_hours: int
    distance: float


class TaskHoursEstimateView(BaseModel):
    module: str
    task: str
    estimated_hours: int | None = None
    reliability: float | None = None
    dispersion: float | None = None
    has_match: bool
    neighbors: list[TaskNeighborView] = Field(default_factory=list)


class TaskHoursResultView(BaseModel):
    tasks: list[TaskHoursEstimateView]
