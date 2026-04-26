"""Few-shot estimation examples injected into the system prompt."""

from pydantic import BaseModel, Field


class EstimationExample(BaseModel):
    """One prior meeting summary paired with its reference estimate."""

    meeting_summary: str = Field(..., min_length=1)
    estimation: str = Field(..., min_length=1)


EXAMPLES: list[EstimationExample] = [
    EstimationExample(
        meeting_summary=(
            "The client wants a small internal dashboard to visualize sales KPIs "
            "from a CSV export refreshed daily. Authentication is SSO via their "
            "existing IdP. They need filters by region and export to PDF."
        ),
        estimation=(
            "## Estimation: Sales KPI dashboard\n\n"
            "### Assumptions\n"
            "- CSV schema is stable; ingestion is batch, not streaming.\n"
            "- SSO integration uses SAML or OIDC as documented by the IdP team.\n\n"
            "### Tasks\n"
            "| Task | Hours |\n"
            "|------|------:|\n"
            "| Data ingest + validation | 12 |\n"
            "| Charts + filters UI | 16 |\n"
            "| SSO + roles | 10 |\n"
            "| PDF export | 6 |\n"
            "| QA + hardening | 10 |\n"
            "| **Total** | **54** |\n\n"
            "### Delivery notes\n"
            "Target 2 calendar weeks with one mid-sprint review."
        ),
    ),
    EstimationExample(
        meeting_summary=(
            "Mobile app MVP: user registration, profile, and a map showing nearby "
            "service providers. Push notifications when a provider accepts a job. "
            "Backend should expose a REST API; admin panel is out of scope."
        ),
        estimation=(
            "## Estimation: Service marketplace MVP (mobile)\n\n"
            "### Assumptions\n"
            "- One client platform first (iOS or Android), second platform +20% effort.\n"
            "- Map uses vendor SDK with documented quotas.\n\n"
            "### Tasks\n"
            "| Task | Hours |\n"
            "|------|------:|\n"
            "| API design + auth | 20 |\n"
            "| Provider matching + state machine | 24 |\n"
            "| Mobile UI flows | 36 |\n"
            "| Push notifications | 10 |\n"
            "| Observability + release | 10 |\n"
            "| **Total** | **100** |\n\n"
            "### Delivery notes\n"
            "Plan 4 two-week sprints; defer admin UI."
        ),
    ),
]


def load_examples() -> list[EstimationExample]:
    """Return the static few-shot examples for prompting."""

    return list(EXAMPLES)
