"""Langfuse-backed observability adapter (OpenTelemetry SDK integration)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langfuse import propagate_attributes

from app.services.observability.metadata import merge_trace_tags, stringify_metadata
from app.services.observability.types import TelemetryContext

logger = logging.getLogger(__name__)


class LangfuseObservabilityAdapter:
    """Export traces/spans/generations via the Langfuse Python SDK."""

    def __init__(
        self,
        langfuse_client: Any,
        *,
        app_env: str,
        app_version: str,
        app_release: str,
        capture_inputs: bool,
        capture_outputs: bool,
        capture_usage: bool,
        capture_cost: bool,
    ) -> None:
        self._langfuse = langfuse_client
        self._app_env = app_env
        self._app_version = app_version
        self._app_release = app_release
        self._capture_inputs = capture_inputs
        self._capture_outputs = capture_outputs
        self._capture_usage = capture_usage
        self._capture_cost = capture_cost
        self._prompt_version: str | None = None
        self._examples_version: str | None = None
        self._extra_tags: list[str] = []

    @contextmanager
    def start_trace(
        self,
        name: str,
        *,
        context: TelemetryContext,
        input: Any | None = None,
    ) -> Iterator[Any]:
        merged_metadata: dict[str, Any] = {
            "request_id": context.request_id,
            "feature": context.feature,
            "app_env": self._app_env,
            "version": self._app_version,
            "release": self._app_release,
            **context.metadata,
        }
        merged_tags = merge_trace_tags(
            app_env=self._app_env,
            feature=context.feature,
            app_release=self._app_release,
            extra_tags=[*context.tags, *self._extra_tags],
        )

        with propagate_attributes(
            user_id=context.user_id,
            session_id=context.session_id,
            version=self._app_version,
            metadata=stringify_metadata(merged_metadata),
            tags=merged_tags,
        ):
            with self._langfuse.start_as_current_observation(
                as_type="span",
                name=name,
                input=input,
                metadata=merged_metadata,
            ) as span:
                yield span

    @contextmanager
    def start_span(
        self,
        name: str,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> Iterator[Any]:
        with self._langfuse.start_as_current_observation(
            as_type="span",
            name=name,
            metadata=attributes,
        ) as span:
            yield span

    @contextmanager
    def start_generation(
        self,
        name: str,
        *,
        model: str,
        input: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[Any]:
        generation_metadata: dict[str, Any] = dict(metadata or {})
        if self._prompt_version:
            generation_metadata.setdefault("prompt_version", self._prompt_version)
        if self._examples_version:
            generation_metadata.setdefault("examples_version", self._examples_version)

        generation_input = input if self._capture_inputs else None

        with self._langfuse.start_as_current_observation(
            as_type="generation",
            name=name,
            model=model,
            input=generation_input,
            metadata=generation_metadata,
        ) as generation:
            yield generation

    def update_generation_usage(self, usage_details: dict[str, int]) -> None:
        if not self._capture_usage:
            return
        try:
            self._langfuse.update_current_generation(usage_details=usage_details)
        except Exception as exc:  # noqa: BLE001 — observability must not break LLM path
            logger.warning(
                "langfuse_update_generation_usage_failed",
                extra={"event": "langfuse_update_generation_usage_failed", "error_type": type(exc).__name__},
            )

    def update_generation_cost(self, cost_details: dict[str, float]) -> None:
        if not self._capture_cost:
            return
        try:
            self._langfuse.update_current_generation(cost_details=cost_details)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "langfuse_update_generation_cost_failed",
                extra={"event": "langfuse_update_generation_cost_failed", "error_type": type(exc).__name__},
            )

    def update_generation_output(self, output: Any) -> None:
        if not self._capture_outputs:
            return
        try:
            self._langfuse.update_current_generation(output=output)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "langfuse_update_generation_output_failed",
                extra={"event": "langfuse_update_generation_output_failed", "error_type": type(exc).__name__},
            )

    def update_generation_metadata(self, metadata: dict[str, Any]) -> None:
        try:
            self._langfuse.update_current_generation(metadata=metadata)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "langfuse_update_generation_metadata_failed",
                extra={
                    "event": "langfuse_update_generation_metadata_failed",
                    "error_type": type(exc).__name__,
                },
            )

    def record_error(
        self,
        error: BaseException,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        safe_error = {
            "error_type": type(error).__name__,
            "error_message": str(error)[:500],
        }
        metadata = {**(attributes or {}), "error": safe_error}
        logger.warning(
            "estimator_operation_failed",
            extra={"event": "estimator_operation_failed", **safe_error},
        )
        try:
            self._langfuse.update_current_span(metadata=metadata)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "langfuse_record_error_failed",
                extra={"event": "langfuse_record_error_failed", "error_type": type(exc).__name__},
            )

    def set_user_context(self, user_id: str | None) -> None:
        del user_id

    def set_session_context(self, session_id: str | None) -> None:
        del session_id

    def set_prompt_context(
        self,
        *,
        prompt_version: str,
        examples_version: str | None = None,
    ) -> None:
        self._prompt_version = prompt_version
        self._examples_version = examples_version

    def add_tags(self, *tags: str) -> None:
        self._extra_tags.extend(tags)

    def set_http_status(self, status_code: int) -> None:
        status_class = f"{status_code // 100}xx"
        metadata = {
            "http.status_code": status_code,
            "http.status_class": status_class,
        }
        try:
            self._langfuse.update_current_span(metadata=metadata)
            self.add_tags(f"http_status:{status_class}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "langfuse_set_http_status_failed",
                extra={
                    "event": "langfuse_set_http_status_failed",
                    "error_type": type(exc).__name__,
                    "http_status_code": status_code,
                },
            )

    def flush(self) -> None:
        try:
            self._langfuse.flush()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "langfuse_flush_failed",
                extra={"event": "langfuse_flush_failed", "error_type": type(exc).__name__},
            )
