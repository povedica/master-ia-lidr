"""HTTP API tests."""

import json
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
    async def estimate(self, transcription: str, **_: object) -> EstimationResult:
        return EstimationResult(
            estimation=(
                "## Estimation: mocked output\n\n"
                "### Assumptions\nx\n### Estimate\ny\n### Risks\nz\n"
            ),
            provider="openai",
            model="gpt-4o-mini",
            usage=UsageInfo(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            mode=EstimationMode.BASIC,
            assessment=None,
            mode_eligibility=None,
            finish_reason="stop",
        )

    async def stream_estimation(self, transcription: str, **_: object):
        del transcription
        yield 'event: chunk\ndata: {"content":"## Estimation: mocked output"}\n\n'
        yield 'event: done\ndata: {"status":"completed"}\n\n'


class _FakeStaticFallbackEstimationService:
    async def estimate(self, transcription: str, **_: object) -> EstimationResult:
        return EstimationResult(
            estimation="## Estimation: fallback output",
            provider="static_fallback",
            model="static-v1",
            usage=None,
            mode=EstimationMode.BASIC,
            assessment=None,
            mode_eligibility=None,
            degraded=True,
            finish_reason="stop",
        )


class _FailingEstimationService:
    async def estimate(self, transcription: str, **_: object) -> str:
        raise EstimationError("OpenAI API key is not configured.")


class _OutOfDomainEstimationService:
    async def estimate(self, transcription: str, **_: object) -> str:
        raise DomainGuardrailError("Only software/project estimation requests are supported.")


class _FailingStreamEstimationService:
    async def estimate(self, transcription: str, **_: object) -> str:
        del transcription
        raise EstimationError("not used")

    async def stream_estimation(self, transcription: str, **_: object):
        del transcription
        yield 'event: error\ndata: {"message":"All providers failed."}\n\n'


def test_root_returns_service_index() -> None:
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "Estimador CAG"
    assert body["docs"] == "/docs"
    assert body["health"] == "/health"
    assert "estimate" in body
    assert body.get("estimate_stream") == "POST /api/v1/estimate/stream"


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
                    "evaluate": False,
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
    assert body["prompt_version"] == "v6"
    assert body["examples_version"] == "file-mode-v4-estimator-layout"
    assert body["usage"]["total_tokens"] == 150
    assert body["usage"]["preprocessing_input_tokens"] == 0
    assert body["usage"]["preprocessing_output_tokens"] == 0
    assert body["usage"]["estimated_cost_usd"] > 0
    assert "score" not in body
    assert body["finish_reason"] == "stop"


def test_estimate_returns_estimator_scoring_by_default() -> None:
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
    assert body["score"] == 0.25
    assert body["structure_evaluation"] is not None
    assert body["structure_evaluation"]["score"] == body["score"]
    assert body["output_validation"] is not None
    assert body["output_validation"]["finish_reason_ok"] is True
    assert body["output_validation"]["mode"] == "basic"


def test_estimate_rejects_invalid_preprocessing() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/estimate",
            json={"transcription": "Client wants a landing page.", "preprocessing": "invalid"},
        )
    assert response.status_code == 422


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
                    "evaluate": False,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body.keys() == {"estimation"}
    assert "output_validation" not in body
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
                    "evaluate": False,
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
                json={
                    "transcription": "Client wants a landing page with a contact form.",
                    "evaluate": False,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "static_fallback"
    assert body["mode"] == "basic"
    assert body["degraded"] is True
    assert "score" not in body
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
                json={
                    "transcription": "Client wants a landing page with a contact form.",
                    "evaluate": False,
                },
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


def test_estimate_appends_stats_jsonl_when_stats_log_enabled(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "usage.jsonl"
    app.dependency_overrides[get_estimation_service] = lambda: _FakeEstimationService()  # type: ignore[return-value]
    app.dependency_overrides[get_settings] = lambda: Settings(
        openai_api_key="sk-test",
        dev_mode=False,
        openai_model="gpt-4o-mini",
        estimation_stats_log_enabled=True,
        estimation_stats_log_path=str(log_path),
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/estimate",
                json={
                    "transcription": "Client wants a landing page with a contact form.",
                    "evaluate": False,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json().keys() == {"estimation"}
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert "estimation" not in row
    assert row["provider"] == "openai"
    assert row["mode"] == "basic"
    assert row["request_id"].startswith("est_")
    assert row["usage"]["total_tokens"] == 150
    assert row["usage"]["preprocessing_input_tokens"] == 0
    assert row["usage"]["preprocessing_output_tokens"] == 0
    assert row["score"] == 0.25
    assert row["finish_reason"] == "stop"


def test_estimate_does_not_persist_output_for_422_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(response_output_writer, "_OUTPUT_DIR", tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/v1/estimate", json={})

    assert response.status_code == 422
    assert list(tmp_path.glob("response-*.md")) == []


def test_estimate_stream_returns_sse_done_event() -> None:
    app.dependency_overrides[get_estimation_service] = lambda: _FakeEstimationService()  # type: ignore[return-value]
    app.dependency_overrides[get_settings] = lambda: Settings(
        openai_api_key="sk-test",
        dev_mode=True,
    )
    try:
        with TestClient(app) as client:
            with client.stream(
                "POST",
                "/api/v1/estimate/stream",
                json={"transcription": "Client wants a landing page with a contact form."},
            ) as response:
                body = response.read().decode("utf-8")
                content_type = response.headers.get("content-type", "")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert content_type.startswith("text/event-stream")
    assert "event: done" in body
    assert 'data: {"status":"completed"}' in body


def test_estimate_stream_emits_error_event_on_service_failure() -> None:
    app.dependency_overrides[get_estimation_service] = lambda: _FailingStreamEstimationService()  # type: ignore[return-value]
    app.dependency_overrides[get_settings] = lambda: Settings(openai_api_key="sk-test", dev_mode=True)
    try:
        with TestClient(app) as client:
            with client.stream(
                "POST",
                "/api/v1/estimate/stream",
                json={"transcription": "Client wants a landing page with a contact form."},
            ) as response:
                body = response.read().decode("utf-8")
                headers = response.headers
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert headers.get("cache-control") == "no-cache"
    assert headers.get("x-accel-buffering") == "no"
    assert "event: error" in body
    assert "All providers failed." in body
