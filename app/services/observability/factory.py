"""Resolve the process-wide observability adapter from settings."""

from __future__ import annotations

from langfuse import Langfuse

from app.config import Settings
from app.services.observability.langfuse_adapter import LangfuseObservabilityAdapter
from app.services.observability.noop import NoopObservabilityAdapter
from app.services.observability.types import ObservabilityAdapter


def build_observability_adapter(settings: Settings) -> ObservabilityAdapter:
    """Return Langfuse adapter when export is active; noop otherwise."""

    if not settings.observability_export_active():
        return NoopObservabilityAdapter()

    client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url,
        environment=settings.app_env,
        release=settings.app_release,
        debug=settings.langfuse_debug,
        sample_rate=settings.langfuse_sample_rate,
    )
    return LangfuseObservabilityAdapter(
        client,
        app_env=settings.app_env,
        app_version=settings.app_version,
        app_release=settings.app_release,
        capture_inputs=settings.langfuse_capture_inputs,
        capture_outputs=settings.langfuse_capture_outputs,
        capture_usage=settings.langfuse_capture_usage,
        capture_cost=settings.langfuse_capture_cost,
    )
