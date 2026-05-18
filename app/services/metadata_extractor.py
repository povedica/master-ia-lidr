"""LLM-backed extraction of distilled project metadata from conversation turns."""

from __future__ import annotations

from app.services.structured_llm_client import StructuredCompletionError, complete_structured
from app.services.sessions import ProjectMetadata

_LIST_FIELDS = frozenset({"mentioned_technologies", "explicit_constraints", "rejected_options"})

_EXTRACTION_SYSTEM = (
    "You extract structured project metadata from the latest user and assistant turns. "
    "Return only fields that changed or were newly mentioned. "
    "Use null for scalars the user explicitly revoked. "
    "For lists, return only new items to append, or rejected options when the user "
    "clearly rejects a prior choice."
)


class MetadataExtractionError(RuntimeError):
    """Raised when metadata extraction cannot complete after retries."""


def _append_unique_items(current: list[str], additions: list[str]) -> list[str]:
    result = list(current)
    seen = {item.lower() for item in result}
    for item in additions:
        key = item.lower()
        if key not in seen:
            result.append(item)
            seen.add(key)
    return result


def merge_project_metadata(current: ProjectMetadata, patch: ProjectMetadata) -> ProjectMetadata:
    """Apply validated extractor output onto existing session metadata."""

    merged = current.model_copy(deep=True)
    for name in patch.model_fields_set:
        value = getattr(patch, name)
        if name in _LIST_FIELDS:
            setattr(merged, name, _append_unique_items(getattr(merged, name), value))
        else:
            setattr(merged, name, value)

    if merged.rejected_options:
        rejected_lower = {item.lower() for item in merged.rejected_options}
        merged.mentioned_technologies = [
            tech
            for tech in merged.mentioned_technologies
            if tech.lower() not in rejected_lower
        ]
    return merged


def _build_extraction_user_prompt(
    current: ProjectMetadata,
    user_turn: str,
    assistant_turn: str,
) -> str:
    return (
        "Current metadata JSON:\n"
        f"{current.model_dump_json()}\n\n"
        f"Latest user turn:\n{user_turn.strip()}\n\n"
        f"Latest assistant turn:\n{assistant_turn.strip()}"
    )


async def extract_and_merge_metadata(
    current: ProjectMetadata,
    *,
    user_turn: str,
    assistant_turn: str,
    litellm_model: str,
    chain_provider: str,
    api_key: str,
    timeout_seconds: float,
    max_attempts: int,
    max_output_tokens: int = 800,
) -> ProjectMetadata:
    """Run structured extraction and merge the patch into ``current``."""

    try:
        patch, _, _ = await complete_structured(
            litellm_model=litellm_model,
            chain_provider=chain_provider,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            system_prompt=_EXTRACTION_SYSTEM,
            user_prompt=_build_extraction_user_prompt(current, user_turn, assistant_turn),
            max_output_tokens=max_output_tokens,
            response_model=ProjectMetadata,
            max_attempts=max_attempts,
        )
    except StructuredCompletionError as exc:
        raise MetadataExtractionError(str(exc)) from exc

    return merge_project_metadata(current, patch)
