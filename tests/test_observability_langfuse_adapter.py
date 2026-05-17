"""Langfuse observability adapter tests (fake client, no network)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.services.observability.langfuse_adapter import LangfuseObservabilityAdapter
from app.services.observability.types import TelemetryContext


class _FakeObservation:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def update(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


class FakeLangfuseClient:
    """Minimal Langfuse client double for unit tests."""

    def __init__(self) -> None:
        self.start_calls: list[dict[str, Any]] = []
        self.generation_updates: list[dict[str, Any]] = []
        self.span_updates: list[dict[str, Any]] = []
        self.flush_count = 0

    @contextmanager
    def start_as_current_observation(self, **kwargs: Any):
        self.start_calls.append(kwargs)
        yield _FakeObservation()

    def update_current_generation(self, **kwargs: Any) -> None:
        self.generation_updates.append(kwargs)

    def update_current_span(self, **kwargs: Any) -> None:
        self.span_updates.append(kwargs)

    def flush(self) -> None:
        self.flush_count += 1


@pytest.fixture
def adapter() -> LangfuseObservabilityAdapter:
    return LangfuseObservabilityAdapter(
        FakeLangfuseClient(),
        app_env="test",
        app_version="0.0.0-test",
        app_release="test-release",
        capture_inputs=False,
        capture_outputs=False,
        capture_usage=True,
        capture_cost=True,
    )


def test_start_trace_calls_propagate_and_span_observation(adapter: LangfuseObservabilityAdapter) -> None:
    fake = adapter._langfuse
    assert isinstance(fake, FakeLangfuseClient)
    ctx = TelemetryContext(
        request_id="req_abc",
        feature="estimation",
        session_id="sess_1",
        tags=["mode:standard"],
    )
    propagate = MagicMock()
    propagate.return_value.__enter__ = MagicMock(return_value=None)
    propagate.return_value.__exit__ = MagicMock(return_value=False)

    with patch("app.services.observability.langfuse_adapter.propagate_attributes", propagate):
        with adapter.start_trace("estimator.api.v2.estimate", context=ctx, input={"k": "v"}):
            pass

    propagate.assert_called_once()
    call_kwargs = propagate.call_args.kwargs
    assert call_kwargs["session_id"] == "sess_1"
    assert call_kwargs["version"] == "0.0.0-test"
    assert "env:test" in call_kwargs["tags"]

    assert len(fake.start_calls) == 1
    span_call = fake.start_calls[0]
    assert span_call["name"] == "estimator.api.v2.estimate"
    assert span_call["as_type"] == "span"
    assert span_call["metadata"]["request_id"] == "req_abc"
    assert span_call["metadata"]["feature"] == "estimation"


def test_start_generation_uses_generation_type_and_model(adapter: LangfuseObservabilityAdapter) -> None:
    fake = adapter._langfuse
    assert isinstance(fake, FakeLangfuseClient)

    with adapter.start_generation(
        "estimator.llm.generate",
        model="openai/gpt-4o-mini",
        input=[{"role": "user", "content": "hi"}],
        metadata={"provider": "openai"},
    ):
        adapter.update_generation_usage({"prompt_tokens": 10, "completion_tokens": 5})

    assert len(fake.start_calls) == 1
    gen_call = fake.start_calls[0]
    assert gen_call["as_type"] == "generation"
    assert gen_call["model"] == "openai/gpt-4o-mini"
    assert gen_call["input"] is None
    assert gen_call["metadata"]["provider"] == "openai"

    assert fake.generation_updates == [{"usage_details": {"prompt_tokens": 10, "completion_tokens": 5}}]


def test_flush_delegates_to_client(adapter: LangfuseObservabilityAdapter) -> None:
    adapter.flush()
    assert adapter._langfuse.flush_count == 1


def test_factory_returns_langfuse_adapter_when_export_active() -> None:
    from app.config import Settings
    from app.services.observability.factory import build_observability_adapter
    from app.services.observability.langfuse_adapter import LangfuseObservabilityAdapter

    settings = Settings(
        _env_file=None,
        otel_export_enabled=True,
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
    )
    with patch("app.services.observability.factory.Langfuse") as langfuse_cls:
        langfuse_cls.return_value = FakeLangfuseClient()
        built = build_observability_adapter(settings)
    assert isinstance(built, LangfuseObservabilityAdapter)
