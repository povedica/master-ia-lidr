"""Structure-only RAG output for task-hours wizard (feature-062)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RagStructureTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class RagStructureModule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200)
    tasks: list[RagStructureTask] = Field(min_length=1)


class RagStructureResult(BaseModel):
    """Module/task decomposition without hours (Session 10 structure pass)."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(..., min_length=20, max_length=2000)
    modules: list[RagStructureModule] = Field(min_length=1)
