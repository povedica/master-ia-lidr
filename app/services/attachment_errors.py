"""Safe attachment failure types mapped to HTTP responses."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AttachmentError(Exception):
    """Deterministic attachment resolution or extraction failure."""

    status_code: int
    code: str
    message: str

    def __str__(self) -> str:
        return self.message
