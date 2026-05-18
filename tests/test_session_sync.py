"""Tests for deterministic session ↔ form sync."""

from __future__ import annotations

from tests.estimation_fixtures import minimal_estimation_request_dict

from app.schemas.estimation_request import EstimationRequest
from app.services.session_sync import (
    build_form_metadata_render_context,
    sync_session_from_request,
)
from app.services.sessions import Session


def test_sync_session_stores_last_request() -> None:
    session = Session(session_id="s1")
    request = EstimationRequest(**minimal_estimation_request_dict(project_name="Portal X"))

    sync_session_from_request(session, request)

    assert session.last_estimation_request is not None
    assert session.last_estimation_request.project_name == "Portal X"


def test_build_form_metadata_includes_populated_fields_only() -> None:
    request = EstimationRequest(**minimal_estimation_request_dict(project_name="Portal X"))
    ctx = build_form_metadata_render_context(request)

    assert ctx["project_name"] == "Portal X"
    assert "project_summary" in ctx
    assert "project_type" in ctx
