"""Map in-memory session aggregates to API summary rows."""

from __future__ import annotations

from app.schemas.session_estimation import SessionSummary
from app.services.sessions import Session


def session_to_summary(session: Session) -> SessionSummary:
    """Build a list-view summary from session state."""

    project_name: str | None = None
    if session.last_estimation_request is not None:
        project_name = session.last_estimation_request.project_name
    return SessionSummary(
        session_id=session.session_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        submit_count=session.submit_count,
        project_name=project_name,
    )
