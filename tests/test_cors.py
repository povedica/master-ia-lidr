"""CORS middleware wiring (origins from typed settings)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.cors import configure_cors


def test_cors_preflight_allows_configured_origin() -> None:
    app = FastAPI()

    @app.post("/echo")
    def echo() -> dict[str, str]:
        return {"ok": "true"}

    configure_cors(
        app,
        Settings(
            _env_file=None,
            openai_api_key="sk-test",
            frontend_origins="http://localhost:5173,http://127.0.0.1:5173",
        ),
    )

    with TestClient(app) as client:
        response = client.options(
            "/echo",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_post_includes_allow_origin_header() -> None:
    app = FastAPI()

    @app.post("/echo")
    def echo() -> dict[str, str]:
        return {"ok": "true"}

    configure_cors(
        app,
        Settings(
            _env_file=None,
            openai_api_key="sk-test",
            frontend_origins="http://localhost:5173",
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/echo",
            headers={"Origin": "http://localhost:5173"},
        )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_skipped_when_origin_list_empty() -> None:
    app = FastAPI()

    @app.post("/echo")
    def echo() -> dict[str, str]:
        return {"ok": "true"}

    configure_cors(
        app,
        Settings(
            _env_file=None,
            openai_api_key="sk-test",
            frontend_origins="",
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/echo",
            headers={"Origin": "http://localhost:5173"},
        )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") is None
