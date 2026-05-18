"""Schemas for session-scoped estimation HTTP API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SessionSummary(BaseModel):
    """Summary row for ``GET /api/v1/sessions``."""

    session_id: str
    created_at: datetime
    updated_at: datetime
    submit_count: int = Field(ge=0)
    project_name: str | None = None
