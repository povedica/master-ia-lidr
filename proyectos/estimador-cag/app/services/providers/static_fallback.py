"""Static degraded fallback provider."""

from __future__ import annotations

from app.services.providers.base import ProviderResult

_STATIC_FALLBACK_RESPONSE = (
    "## Estimation: Temporary degraded mode\n\n"
    "### Assumptions\n"
    "- Live model providers are currently unavailable.\n"
    "- This response is a coarse fallback and should be reviewed manually.\n\n"
    "### Tasks\n"
    "| Task | Hours |\n"
    "|------|------:|\n"
    "| Requirements clarification | 4 |\n"
    "| Technical design draft | 6 |\n"
    "| Implementation + tests | 16 |\n"
    "| QA + deployment checklist | 6 |\n"
    "| **Total** | **32** |\n\n"
    "### Delivery notes\n"
    "Re-run the estimate when model providers recover to replace this degraded output."
)


class StaticFallbackProvider:
    """Deterministic fallback provider used as last resort."""

    name = "static_fallback"
    model = "static-v1"

    async def complete(self, system_prompt: str, user_prompt: str) -> ProviderResult:
        del system_prompt
        del user_prompt
        return ProviderResult(
            text=_STATIC_FALLBACK_RESPONSE,
            provider=self.name,
            model=self.model,
            usage=None,
        )

