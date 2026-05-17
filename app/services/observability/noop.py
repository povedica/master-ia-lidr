"""No-op observability adapter when export is disabled or unavailable."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.services.observability.types import TelemetryContext


class NoopObservabilityAdapter:
    """Same API as the Langfuse adapter; performs no network I/O."""

    @contextmanager
    def start_trace(
        self,
        name: str,
        *,
        context: TelemetryContext,
        input: Any | None = None,
    ) -> Iterator[Any]:
        del name, context, input
        yield None

    @contextmanager
    def start_span(
        self,
        name: str,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> Iterator[Any]:
        del name, attributes
        yield None

    @contextmanager
    def start_generation(
        self,
        name: str,
        *,
        model: str,
        input: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[Any]:
        del name, model, input, metadata
        yield None

    def update_generation_usage(self, usage_details: dict[str, int]) -> None:
        del usage_details

    def update_generation_cost(self, cost_details: dict[str, float]) -> None:
        del cost_details

    def update_generation_output(self, output: Any) -> None:
        del output

    def update_generation_metadata(self, metadata: dict[str, Any]) -> None:
        del metadata

    def record_error(
        self,
        error: BaseException,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        del error, attributes

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
        del prompt_version, examples_version

    def add_tags(self, *tags: str) -> None:
        del tags

    def set_http_status(self, status_code: int) -> None:
        del status_code

    def flush(self) -> None:
        return None
