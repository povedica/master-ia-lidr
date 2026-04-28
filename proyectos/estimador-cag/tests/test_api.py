"""HTTP API tests."""

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.routers.estimations import get_estimation_service
from app.services.llm_service import EstimationError, EstimationResult, UsageInfo


class _FakeEstimationService:
    async def estimate(self, transcription: str) -> EstimationResult:
        return EstimationResult(
            estimation="## Estimation: mocked output",
            provider="openai",
            model="gpt-4o-mini",
            usage=UsageInfo(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        )


class _FakeStaticFallbackEstimationService:
    async def estimate(self, transcription: str) -> EstimationResult:
        return EstimationResult(
            estimation="## Estimation: fallback output",
            provider="static_fallback",
            model="static-v1",
            usage=None,
            degraded=True,
        )


class _FailingEstimationService:
    async def estimate(self, transcription: str) -> str:
        raise EstimationError("OpenAI API key is not configured.")


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
    assert body["request_id"].startswith("est_")
    assert body["timestamp"]
    assert isinstance(body["latency_ms"], int)
    assert body["latency_ms"] >= 0
    assert body["prompt_version"] == "v1"
    assert body["examples_version"] == "static-v1"
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
    assert "usage" not in body


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
    assert body["degraded"] is True
    assert "usage" not in body


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
