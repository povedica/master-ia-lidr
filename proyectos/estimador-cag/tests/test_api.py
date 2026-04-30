"""HTTP API tests."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.routers.estimations import get_estimation_service
from app.services import response_output_writer
from app.services.estimation_engine import EstimationMode
from app.services.llm_service import (
    DomainGuardrailError,
    EstimationError,
    EstimationResult,
    UsageInfo,
)


class _FakeEstimationService:
    async def estimate(self, transcription: str) -> EstimationResult:
        return EstimationResult(
            estimation="## Estimation: mocked output",
            provider="openai",
            model="gpt-4o-mini",
            usage=UsageInfo(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            mode=EstimationMode.BASIC,
            assessment=None,
            mode_eligibility=None,
        )


class _FakeStaticFallbackEstimationService:
    async def estimate(self, transcription: str) -> EstimationResult:
        return EstimationResult(
            estimation="## Estimation: fallback output",
            provider="static_fallback",
            model="static-v1",
            usage=None,
            mode=EstimationMode.BASIC,
            assessment=None,
            mode_eligibility=None,
            degraded=True,
        )


class _FailingEstimationService:
    async def estimate(self, transcription: str) -> str:
        raise EstimationError("OpenAI API key is not configured.")


class _OutOfDomainEstimationService:
    async def estimate(self, transcription: str) -> str:
        raise DomainGuardrailError("Only software/project estimation requests are supported.")


def test_root_returns_service_index() -> None:
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "Estimador CAG"
    assert body["docs"] == "/docs"
    assert body["health"] == "/health"
    assert "estimate" in body


def test_health_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_estimate_returns_expected_shape_with_mocked_service() -> None:
    app.dependency_overrides[get_estimation_service] = lambda: _FakeEstimationService()  # type: ignore[return-value]
    app.dependency_overrides[get_settings] = lambda: Settings(
        openai_api_key="sk-test",
        dev_mode=True,
        openai_model="gpt-4o-mini",
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/estimate",
                json={
                    "transcription": "Client wants a landing page with a contact form.",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["estimation"].startswith("## Estimation")
    assert body["provider"] == "openai"
    assert body["model"] == "gpt-4o-mini"
    assert body["mode"] == "basic"
    assert body["request_id"].startswith("est_")
    assert body["timestamp"]
    assert isinstance(body["latency_ms"], int)
    assert body["latency_ms"] >= 0
    assert body["prompt_version"] == "v5"
    assert body["examples_version"] == "file-random-v2"
    assert body["usage"]["total_tokens"] == 150
    assert body["usage"]["estimated_cost_usd"] > 0


def test_estimate_hides_usage_and_cost_when_dev_mode_disabled() -> None:
    app.dependency_overrides[get_estimation_service] = lambda: _FakeEstimationService()  # type: ignore[return-value]
    app.dependency_overrides[get_settings] = lambda: Settings(
        openai_api_key="sk-test",
        dev_mode=False,
        openai_model="gpt-4o-mini",
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/estimate",
                json={
                    "transcription": "Client wants a landing page with a contact form.",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body.keys() == {"estimation"}
    assert "usage" not in body
    assert "mode" not in body
    assert "assessment" not in body


def test_estimate_persists_output_when_toggle_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(response_output_writer, "_OUTPUT_DIR", tmp_path)
    app.dependency_overrides[get_estimation_service] = lambda: _FakeEstimationService()  # type: ignore[return-value]
    app.dependency_overrides[get_settings] = lambda: Settings(
        openai_api_key="sk-test",
        dev_mode=False,
        estimation_output_persist_enabled=True,
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/estimate",
                json={
                    "transcription": "Client wants a landing page with a contact form.",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    created = list(tmp_path.glob("response-*.md"))
    assert len(created) == 1
    assert created[0].read_text(encoding="utf-8") == response.json()["estimation"]


def test_estimate_includes_degraded_only_for_static_fallback() -> None:
    app.dependency_overrides[get_estimation_service] = lambda: _FakeStaticFallbackEstimationService()  # type: ignore[return-value]
    app.dependency_overrides[get_settings] = lambda: Settings(
        openai_api_key="sk-test",
        dev_mode=True,
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": "Client wants a landing page with a contact form."},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "static_fallback"
    assert body["mode"] == "basic"
    assert body["degraded"] is True
    assert "usage" not in body


def test_estimate_non_dev_surfaces_degraded_only_for_static_fallback() -> None:
    app.dependency_overrides[get_estimation_service] = lambda: _FakeStaticFallbackEstimationService()  # type: ignore[return-value]
    app.dependency_overrides[get_settings] = lambda: Settings(
        openai_api_key="sk-test",
        dev_mode=False,
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": "Client wants a landing page with a contact form."},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body.keys() == {"estimation", "degraded"}
    assert body["degraded"] is True


def test_estimate_validation_error_on_missing_transcription() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/estimate", json={})
    assert response.status_code == 422


def test_estimate_validation_error_on_blank_transcription() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/estimate", json={"transcription": "   "})
    assert response.status_code == 422


def test_estimate_returns_503_when_service_raises_estimation_error() -> None:
    app.dependency_overrides[get_estimation_service] = lambda: _FailingEstimationService()  # type: ignore[return-value]
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": "Any text"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_estimate_returns_422_for_out_of_domain() -> None:
    app.dependency_overrides[get_estimation_service] = lambda: _OutOfDomainEstimationService()  # type: ignore[return-value]
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": "Que distancia hay desde la tierra al sol?"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    body = response.json()
    assert body["detail"]["code"] == "out_of_domain"
    assert "Only software/project estimation requests are supported." in body["detail"]["message"]


def test_estimate_does_not_persist_output_for_503_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(response_output_writer, "_OUTPUT_DIR", tmp_path)
    app.dependency_overrides[get_estimation_service] = lambda: _FailingEstimationService()  # type: ignore[return-value]
    app.dependency_overrides[get_settings] = lambda: Settings(
        openai_api_key="sk-test",
        estimation_output_persist_enabled=True,
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": "Any text"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert list(tmp_path.glob("response-*.md")) == []


def test_estimate_does_not_persist_output_for_422_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(response_output_writer, "_OUTPUT_DIR", tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/v1/estimate", json={})

    assert response.status_code == 422
    assert list(tmp_path.glob("response-*.md")) == []
