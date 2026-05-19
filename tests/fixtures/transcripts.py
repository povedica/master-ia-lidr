"""Payload builders for simplified session integration tests."""

from __future__ import annotations

from typing import Any

TURN_1: dict[str, Any] = {
    "project_name": "Acme Portal",
    "project_type": "web_saas",
    "target_audience": "b2b_smb",
    "transcript": (
        "We need a B2B SaaS customer portal for Acme Corp. "
        "Stack: Python, FastAPI, PostgreSQL. Team of 4 developers. "
        "Scope: authentication, dashboard, billing integration."
    ),
}

TURN_2: dict[str, Any] = {
    **TURN_1,
    "transcript": (
        "Same Acme Portal project — add Redis caching for session tokens "
        "and keep the existing PostgreSQL datastore."
    ),
}


def build_transcript(*, marker: str, min_len: int = 80) -> str:
    base = f"Project discussion marker={marker}. "
    repeat = max(1, min_len // len(base) + 1)
    return (base * repeat)[: max(min_len, len(base))]


def simplified_submit_payload(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "project_name": "Test Project",
        "project_type": "web_saas",
        "target_audience": "b2b_smb",
        "transcript": build_transcript(marker="default"),
    }
    return {**defaults, **overrides}
