"""LLM-backed query reformulation for RAG retrieval."""

from __future__ import annotations

from app.config import Settings
from app.schemas.estimation_query import EstimationQuery
from app.services.llm_types import LLMProvider
from app.services.provider_routing import resolve_first_litellm_route
from app.services.structured_llm_client import StructuredCompletionError, complete_structured

_REFORMULATION_SYSTEM = (
    "You extract structured search facets for software estimation retrieval. "
    "Return search_facets, component_hints, and sector_filters that help find "
    "relevant historical budget chunks. Keep question as the user's estimation intent."
)


class QueryReformulationError(RuntimeError):
    """Raised when query reformulation cannot complete after retries."""


def _build_reformulation_user_prompt(
    question: str,
    *,
    transcript: str | None,
) -> str:
    parts = [f"Estimation question:\n{question.strip()}"]
    if transcript is not None:
        parts.append(f"Conversation transcript:\n{transcript.strip()}")
    return "\n\n".join(parts)


def _pass_through_query(question: str) -> EstimationQuery:
    return EstimationQuery(
        question=question.strip(),
        search_facets=[],
        component_hints=[],
        sector_filters=[],
    )


def _should_call_llm(*, transcript: str | None, settings: Settings) -> bool:
    if transcript is not None and transcript.strip():
        return True
    return settings.reformulation_enabled


async def reformulate_query(
    question: str,
    *,
    transcript: str | None = None,
    settings: Settings,
    providers: list[LLMProvider],
) -> EstimationQuery:
    """Return retrieval-oriented facets from question and optional transcript."""

    if not _should_call_llm(transcript=transcript, settings=settings):
        return _pass_through_query(question)

    route = resolve_first_litellm_route(providers)
    if route is None:
        raise QueryReformulationError(
            "Query reformulation requires a live LiteLLM provider (configure OpenAI or Anthropic)."
        )

    litellm_model = settings.reformulation_model.strip() or route.litellm_model
    try:
        extracted, _, _ = await complete_structured(
            litellm_model=litellm_model,
            chain_provider=route.provider_name,
            api_key=route.api_key,
            timeout_seconds=route.timeout_seconds,
            system_prompt=_REFORMULATION_SYSTEM,
            user_prompt=_build_reformulation_user_prompt(question, transcript=transcript),
            max_output_tokens=800,
            response_model=EstimationQuery,
            max_attempts=settings.structured_output_max_attempts,
        )
    except StructuredCompletionError as exc:
        raise QueryReformulationError(str(exc)) from exc

    return extracted.model_copy(update={"question": question.strip()})
