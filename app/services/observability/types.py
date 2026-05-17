"""Observability domain types and adapter protocol."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class TelemetryContext:
    """Dimensions shared across a business trace (one estimation request)."""

    request_id: str
    feature: str
    user_id: str | None = None
    session_id: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ObservabilityAdapter(Protocol):
    """Stable observability surface; domain code must not import Langfuse directly."""

    def start_trace(
        self,
        name: str,
        *,
        context: TelemetryContext,
        input: Any | None = None,
    ) -> AbstractContextManager[Any]: ...

    def start_span(
        self,
        name: str,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> AbstractContextManager[Any]: ...

    def start_generation(
        self,
        name: str,
        *,
        model: str,
        input: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AbstractContextManager[Any]: ...

    def update_generation_usage(self, usage_details: dict[str, int]) -> None: ...

    def update_generation_cost(self, cost_details: dict[str, float]) -> None: ...

    def update_generation_output(self, output: Any) -> None: ...

    def update_generation_metadata(self, metadata: dict[str, Any]) -> None: ...

    def record_error(
        self,
        error: BaseException,
        *,
        attributes: dict[str, Any] | None = None,
    ) -> None: ...

    def set_user_context(self, user_id: str | None) -> None: ...

    def set_session_context(self, session_id: str | None) -> None: ...

    def set_prompt_context(
        self,
        *,
        prompt_version: str,
        examples_version: str | None = None,
    ) -> None: ...

    def add_tags(self, *tags: str) -> None: ...

    def set_http_status(self, status_code: int) -> None: ...

    def flush(self) -> None: ...
