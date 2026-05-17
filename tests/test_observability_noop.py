"""Noop observability adapter tests."""

from __future__ import annotations

from app.services.observability.noop import NoopObservabilityAdapter
from app.services.observability.types import TelemetryContext


def test_start_trace_yields_without_side_effects() -> None:
    adapter = NoopObservabilityAdapter()
    ctx = TelemetryContext(request_id="req_1", feature="estimation")
    with adapter.start_trace("estimator.request", context=ctx, input={"safe": True}) as obs:
        assert obs is None
    adapter.flush()


def test_start_generation_context_manager_is_ergonomic() -> None:
    adapter = NoopObservabilityAdapter()
    with adapter.start_generation(
        "estimator.llm.generate",
        model="openai/gpt-4o-mini",
        input=None,
    ) as gen:
        assert gen is None
    adapter.update_generation_usage({"prompt_tokens": 1})
    adapter.update_generation_output("ok")
    adapter.flush()


def test_record_error_does_not_raise() -> None:
    adapter = NoopObservabilityAdapter()
    adapter.record_error(RuntimeError("boom"))
    adapter.flush()


def test_factory_returns_noop_when_export_inactive() -> None:
    from app.config import Settings
    from app.services.observability.factory import build_observability_adapter

    settings = Settings(
        _env_file=None,
        otel_export_enabled=False,
    )
    adapter = build_observability_adapter(settings)
    assert isinstance(adapter, NoopObservabilityAdapter)
