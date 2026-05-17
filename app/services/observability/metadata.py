"""Metadata and tag normalization for Langfuse propagation."""

from __future__ import annotations

from typing import Any


def stringify_metadata(metadata: dict[str, Any] | None) -> dict[str, str]:
    """Coerce metadata values to strings for Langfuse ``propagate_attributes``."""

    if not metadata:
        return {}
    return {str(key): str(value) for key, value in metadata.items()}


def merge_trace_tags(
    *,
    app_env: str,
    feature: str,
    app_release: str,
    extra_tags: list[str] | None = None,
) -> list[str]:
    """Build baseline tags for a business trace."""

    tags = [
        f"env:{app_env}",
        f"feature:{feature}",
        f"release:{app_release}",
    ]
    if extra_tags:
        tags.extend(extra_tags)
    return tags
