"""Structure-only RAG generation for task-hours wizard (feature-062)."""

from __future__ import annotations

from app.config import Settings
from app.schemas.estimation_query import EstimationQuery, compose_search_text
from app.schemas.rag_structure_result import RagStructureResult
from app.services.llm_types import LLMProvider, UsageInfo
from app.services.provider_routing import resolve_first_litellm_route
from app.services.structured_llm_client import StructuredCompletionError, complete_structured

_STRUCTURE_SYSTEM = (
    "You decompose software project estimation briefs into modules and tasks. "
    "Return modules with task names and short descriptions only — no hours, no citations."
)
_STRUCTURE_USER_TEMPLATE = (
    "Decompose this estimation brief into modules and tasks without estimating hours.\n\n"
    "Brief:\n{brief}\n"
)


async def generate_structure(
    query: EstimationQuery,
    *,
    settings: Settings,
    providers: list[LLMProvider],
) -> tuple[RagStructureResult, UsageInfo | None, str | None]:
    route = resolve_first_litellm_route(providers)
    if route is None:
        raise StructuredCompletionError(
            "Structure generation requires a live LiteLLM provider (configure OpenAI or Anthropic)."
        )

    brief = compose_search_text(query)
    result, usage, finish = await complete_structured(
        litellm_model=route.litellm_model,
        chain_provider=route.provider_name,
        api_key=route.api_key,
        timeout_seconds=route.timeout_seconds,
        system_prompt=_STRUCTURE_SYSTEM,
        user_prompt=_STRUCTURE_USER_TEMPLATE.format(brief=brief),
        max_output_tokens=settings.estimation_output_tokens_max,
        response_model=RagStructureResult,
        max_attempts=settings.structured_output_max_attempts,
    )
    return result, usage, finish
