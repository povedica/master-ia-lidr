"""Deterministic sync between guided form submits and session memory."""

from __future__ import annotations

from app.schemas.estimation_request import EstimationRequest
from app.services.sessions import ProjectMetadata, Session


def sync_session_from_request(session: Session, request: EstimationRequest) -> None:
    """Update canonical form snapshot and compact metadata from the latest submit."""

    session.last_estimation_request = request
    session.project_metadata = project_metadata_from_request(request)


def project_metadata_from_request(request: EstimationRequest) -> ProjectMetadata:
    """Derive compact metadata for listing and legacy partials from the guided form."""

    technologies: list[str] = []
    if request.integration_categories:
        technologies.extend(c.value for c in request.integration_categories)
    if request.integration_custom_names:
        technologies.extend(request.integration_custom_names)

    scope_parts = [request.project_summary.strip()]
    description = request.project_description.strip()
    if description:
        scope_parts.append(description[:500])

    return ProjectMetadata(
        project_name=request.project_name,
        assumed_team_size=_team_size_hint(request),
        mentioned_technologies=technologies,
        agreed_scope=" — ".join(p for p in scope_parts if p) or None,
        explicit_constraints=list(request.out_of_scope or [])[:5],
        rejected_options=[],
    )


def _team_size_hint(request: EstimationRequest) -> int | None:
    if request.team_context is None:
        return None
    mapping = {
        "client_only": 2,
        "vendor_led": 5,
        "mixed_team": 6,
        "unknown": None,
    }
    return mapping.get(request.team_context.value)


def build_form_metadata_render_context(request: EstimationRequest) -> dict[str, object]:
    """Jinja context for session system metadata from populated form fields only."""

    ctx: dict[str, object] = {}
    if request.project_name:
        ctx["project_name"] = request.project_name
    ctx["project_summary"] = request.project_summary
    ctx["project_type"] = request.project_type.value
    ctx["target_audience"] = request.target_audience.value
    if request.industry is not None:
        ctx["industry"] = request.industry.value
    ctx["delivery_urgency"] = request.delivery_urgency.value
    if request.detail_level:
        ctx["detail_level"] = request.detail_level.value
    if request.deliverables:
        ctx["deliverables"] = list(request.deliverables)
    meta = project_metadata_from_request(request)
    if meta.assumed_team_size is not None:
        ctx["assumed_team_size"] = meta.assumed_team_size
    if meta.mentioned_technologies:
        ctx["mentioned_technologies"] = meta.mentioned_technologies
    if meta.agreed_scope:
        ctx["agreed_scope"] = meta.agreed_scope
    if meta.explicit_constraints:
        ctx["explicit_constraints"] = meta.explicit_constraints
    return ctx
