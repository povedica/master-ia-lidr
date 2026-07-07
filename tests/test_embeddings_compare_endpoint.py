"""API tests for POST /api/v1/embeddings/compare (feature-063)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import embeddings

COMPARE_PATH = "/api/v1/embeddings/compare"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _budget_payload() -> dict[str, object]:
    return {
        "budgets": [
            {
                "budget_id": "BUD-1",
                "client_metadata": {"name": "Acme", "sector": "retail", "country": "ES"},
                "project_summary": "Checkout rebuild",
                "main_technology": "Python",
                "year": 2025,
                "total_estimated_hours": 80,
                "components": [
                    {
                        "component_id": "c1",
                        "name": "Checkout",
                        "description": "Stripe integration",
                        "tech_stack": ["stripe"],
                        "estimated_hours": 40,
                        "complexity": "medium",
                        "dependencies": [],
                    }
                ],
            }
        ],
        "strategies": ["structural", "recursive", "sentence_window"],
    }


def test_embeddings_compare_returns_three_strategies(client: TestClient) -> None:
    class _FakeEmbedder:
        async def embed_many(self, chunks):
            return chunks

        async def embed_one(self, text: str):
            del text
            return [0.1] * 1536

    app.dependency_overrides[embeddings.get_embedder] = lambda: _FakeEmbedder()  # type: ignore[assignment]
    response = client.post(COMPARE_PATH, json=_budget_payload())
    app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert len(body["stats_per_strategy"]) == 3


def test_embeddings_compare_unknown_strategy_returns_400(client: TestClient) -> None:
    payload = _budget_payload()
    payload["strategies"] = ["unknown"]
    response = client.post(COMPARE_PATH, json=payload)
    assert response.status_code == 400
