"""HTTP API tests."""

from fastapi.testclient import TestClient

from app.main import app
from app.routers.estimations import get_estimation_service
from app.services.llm_service import EstimationError


class _FakeEstimationService:
    async def estimate(self, transcription: str) -> str:
        return "## Estimation: mocked output"


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
    assert body["model"]


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
