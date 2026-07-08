"""Request/response schemas for agentic estimation API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.services.agentic.agent_schemas import AgentEstimate, AgentTrace


class AgentEstimateRequest(BaseModel):
    transcript: str = Field(min_length=1)
    model: str | None = None
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = None
    max_iterations: int | None = Field(default=None, ge=1)


class AgentEstimateResponse(BaseModel):
    result: AgentEstimate | None
    trace: AgentTrace
    request_id: str
    iterations: int = Field(ge=0)
    stopped_reason: Literal["completed", "max_iterations", "no_final_estimate"]
    model: str
