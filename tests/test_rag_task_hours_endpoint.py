"""API tests for POST /api/v1/estimate/rag/tasks/hours (feature-062)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.rag_task_hours import TaskHoursEstimateView, TaskHoursResultView

TASK_HOURS_PATH = "/api/v1/estimate/rag/tasks/hours"


def test_task_hours_endpoint_returns_estimates() -> None:
    client = TestClient(app)
    mocked = TaskHoursResultView(
        tasks=[
            TaskHoursEstimateView(
                module="Auth",
                task="OAuth",
                estimated_hours=16,
                reliability=0.9,
                dispersion=0.1,
                has_match=True,
            )
        ]
    )
    with patch(
        "app.routers.rag_task_hours.estimate_all_tasks",
        new_callable=AsyncMock,
        return_value=mocked,
    ):
        response = client.post(
            TASK_HOURS_PATH,
            json={
                "modules": [
                    {
                        "name": "Auth",
                        "tasks": [{"name": "OAuth", "description": "Google login"}],
                    }
                ]
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["tasks"][0]["has_match"] is True
    assert body["tasks"][0]["estimated_hours"] == 16
