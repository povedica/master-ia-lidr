"""Request schemas for conversational session estimation."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SessionEstimateRequest(BaseModel):
    """Free-text turn payload for session-scoped estimation."""

    user_message: str = Field(..., min_length=1)
