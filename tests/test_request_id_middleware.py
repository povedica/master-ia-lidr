"""Tests for global X-Request-ID middleware (feature-056)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_response_includes_request_id_header() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")


def test_client_supplied_request_id_is_echoed() -> None:
    client = TestClient(app)
    supplied = "req-client-supplied-123"
    response = client.get("/health", headers={"X-Request-ID": supplied})
    assert response.headers.get("X-Request-ID") == supplied
