"""OpenAI client and CAG-style estimation logic."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from openai import APIError, APITimeoutError, AsyncOpenAI, AuthenticationError, RateLimitError

from app.config import Settings
from app.context.examples import EstimationExample, load_examples

logger = logging.getLogger(__name__)
PROMPT_VERSION = "v1"
EXAMPLES_VERSION = "static-v1"


class EstimationError(Exception):
    """Raised when an estimate cannot be produced; message is safe for clients."""


@dataclass(frozen=True)
class UsageInfo:
    """Token usage returned by the provider."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class EstimationResult:
    """Estimation text plus provider metadata used by the API layer."""

    estimation: str
    usage: UsageInfo | None


def build_system_prompt(examples: list[EstimationExample]) -> str:
    """Compose the system message including static few-shot examples."""

    intro = (
        "You are an expert software project estimator. "
        "The following sections are reference patterns: mirror their structure, "
        "level of detail, and pragmatism. Adapt hours and scope to the new meeting.\n"
        "Respond with a structured estimate: assumptions, task table with hours, "
        "and brief delivery notes."
    )
    parts: list[str] = [intro, "\n## Reference estimation examples\n"]
    for index, example in enumerate(examples, start=1):
        parts.append(f"\n### Example {index} — meeting summary\n{example.meeting_summary}\n")
        parts.append(f"\n### Example {index} — estimate\n{example.estimation}\n")
    return "".join(parts)


class EstimationService:
    """Coordinates prompt construction and the OpenAI chat completion call."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def estimate(self, transcription: str) -> EstimationResult:
        """Return generated estimation plus provider usage metadata."""

        text = transcription.strip()
        if not text:
            raise EstimationError("Transcription must not be empty.")

        if self._settings.llm_provider.lower() != "openai":
            raise EstimationError("Only the OpenAI provider is supported in this version.")

        if not self._settings.openai_api_key:
            raise EstimationError("OpenAI API key is not configured.")

        system_prompt = build_system_prompt(load_examples())
        client = AsyncOpenAI(
            api_key=self._settings.openai_api_key,
            timeout=self._settings.openai_timeout_seconds,
        )

        try:
            response = await client.chat.completions.create(
                model=self._settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
            )
        except APITimeoutError as exc:
            logger.warning(
                "llm_request_failed",
                extra={
                    "provider": "openai",
                    "model": self._settings.openai_model,
                    "error_type": type(exc).__name__,
                },
            )
            raise EstimationError("The language model request timed out.") from exc
        except RateLimitError as exc:
            logger.warning(
                "llm_request_failed",
                extra={
                    "provider": "openai",
                    "model": self._settings.openai_model,
                    "error_type": type(exc).__name__,
                },
            )
            raise EstimationError("Rate limit reached. Retry later.") from exc
        except AuthenticationError as exc:
            logger.warning(
                "llm_request_failed",
                extra={
                    "provider": "openai",
                    "model": self._settings.openai_model,
                    "error_type": type(exc).__name__,
                },
            )
            raise EstimationError(
                "OpenAI authentication failed. Check API credentials.",
            ) from exc
        except APIError as exc:
            logger.warning(
                "llm_request_failed",
                extra={
                    "provider": "openai",
                    "model": self._settings.openai_model,
                    "error_type": type(exc).__name__,
                },
            )
            raise EstimationError("The language model provider returned an error.") from exc
        except Exception as exc:
            logger.exception(
                "llm_request_failed",
                extra={
                    "provider": "openai",
                    "model": self._settings.openai_model,
                    "error_type": type(exc).__name__,
                },
            )
            raise EstimationError(
                "An unexpected error occurred while calling the model.",
            ) from exc

        choice = response.choices[0].message if response.choices else None
        content = (choice.content or "").strip() if choice else ""
        if not content:
            logger.warning(
                "llm_empty_response",
                extra={"provider": "openai", "model": self._settings.openai_model},
            )
            raise EstimationError("The model returned an empty response.")

        usage = response.usage
        usage_info = None
        if usage:
            usage_info = UsageInfo(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            )

        return EstimationResult(estimation=content, usage=usage_info)
