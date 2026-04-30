"""Provider abstraction and common provider result/error models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class UsageInfo:
    """Token usage returned by a provider when available."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class ProviderResult:
    """Normalized LLM completion result returned by providers."""

    text: str
    provider: str
    model: str
    usage: UsageInfo | None


class ProviderError(Exception):
    """Base class for provider-level failures."""


class ProviderTimeoutError(ProviderError):
    """Raised when provider request times out."""


class ProviderUnavailableError(ProviderError):
    """Raised when provider is temporarily unavailable or throttled."""


class ProviderInvalidResponseError(ProviderError):
    """Raised when provider returns an empty or invalid response."""


class ProviderConfigError(ProviderError):
    """Raised for provider authentication or runtime configuration issues."""


class LLMProvider(Protocol):
    """Minimal provider interface used by the service chain."""

    name: str
    model: str

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_output_tokens: int,
    ) -> ProviderResult:
        """Return a normalized completion response."""

