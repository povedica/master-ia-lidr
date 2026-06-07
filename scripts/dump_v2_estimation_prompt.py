#!/usr/bin/env python3
"""Dump v2 estimation LLM messages (dry run) to ``output-prompt/``.

Mirrors ``POST /api/v2/estimate`` prompt assembly through ``prepare_structured_prelude``
and ``render_estimation_prompt`` without calling ``complete_structured``.

Usage::

    uv run python scripts/dump_v2_estimation_prompt.py
    uv run python scripts/dump_v2_estimation_prompt.py --prompt-version v1
    uv run python scripts/dump_v2_estimation_prompt.py --preprocessing inline_cleaning

``--preprocessing two_phase`` performs a real LLM extraction call before dumping.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_OUTPUT_DIR = _REPO_ROOT / "output-prompt"

from app.config import Settings  # noqa: E402
from app.context.examples import load_examples  # noqa: E402
from app.schemas.estimation_request import (  # noqa: E402
    Attachment,
    DataSensitivity,
    DeliveryApproach,
    DeliveryUrgency,
    DetailLevel,
    EstimationRequest,
    HostingConstraint,
    Industry,
    IntegrationCategory,
    OutputFormat,
    ProjectType,
    RiskLevel,
    TargetAudience,
    TeamContext,
    UiLanguage,
)
from app.schemas.estimation_result import EstimationResult as DomainEstimationResult  # noqa: E402
from app.services.estimation_prompt_rendering import render_estimation_prompt  # noqa: E402
from app.services.estimation_request_render import render_estimation_assessment_surface  # noqa: E402
from app.services.llm_service import EXAMPLES_VERSION, EstimationService, StructuredPrelude  # noqa: E402
from app.services.prompt_renderer import RenderedPrompt  # noqa: E402
from app.services.prompt_versions import resolve_prompt_bundle_version  # noqa: E402


def build_full_dummy_request() -> EstimationRequest:
    """Rich guided-form payload with all major sections populated."""

    brief_text = (
        "Functional brief (attachment):\n"
        "- SSO via SAML for enterprise tenants\n"
        "- Ticket SLA: P1 4h, P2 1 business day\n"
        "- Quarterly PDF export for account managers\n"
    )
    raw_b64 = base64.b64encode(brief_text.encode("utf-8")).decode("ascii")

    return EstimationRequest(
        project_name="ACME Partner Portal",
        project_summary=(
            "B2B partner portal for support intake, SLA tracking, and quarterly reporting "
            "with CRM handoff planned for a later phase."
        ),
        project_type=ProjectType.web_saas,
        target_audience=TargetAudience.b2b_enterprise,
        industry=Industry.fintech,
        project_description=(
            "The client needs a responsive web application for authenticated partners to submit "
            "structured tickets, follow approval workflows, and view status dashboards. "
            "Phase one covers intake, notifications, and operations views; ERP sync is deferred. "
            "Non-functional requirements include 99.5% monthly uptime, audit logs for admin actions, "
            "and GDPR-aligned retention for ticket attachments stored in EU regions."
        ),
        deliverables=[
            "Partner authentication with SSO and role-based access control",
            "Configurable ticket intake forms with validation and file uploads",
            "Operations dashboards with filters, CSV export, and saved views",
            "Email and in-app notifications for SLA breaches and escalations",
            "Admin console for tenant configuration and user provisioning",
        ],
        out_of_scope=[
            "Native mobile apps (responsive web only in this phase)",
            "Full ERP bidirectional sync with legacy systems",
            "Automated ML classification of inbound tickets",
        ],
        delivery_urgency=DeliveryUrgency.fixed_date,
        target_date=date(2026, 9, 30),
        delivery_approach=DeliveryApproach.phased_roadmap,
        integration_categories=[
            IntegrationCategory.crm,
            IntegrationCategory.payments,
            IntegrationCategory.identity_sso,
        ],
        integration_custom_names=["Legacy billing hub (read-only export)"],
        data_sensitivity=DataSensitivity.pii_light,
        hosting_constraints=[HostingConstraint.cloud_managed, HostingConstraint.hybrid],
        hosting_notes="Production in EU (Frankfurt); DR warm standby in EU-West.",
        team_context=TeamContext.mixed_team,
        ui_languages=[UiLanguage.en, UiLanguage.es],
        risk_level=RiskLevel.medium,
        external_dependencies=[
            "Identity provider SAML metadata from client security team",
            "Third-party email provider API approval before go-live",
        ],
        detail_level=DetailLevel.detailed,
        output_format=OutputFormat.phases_table,
        attachments=[
            Attachment(
                filename="functional-brief.txt",
                content_type="text/plain",
                content_base64=raw_b64,
            )
        ],
        preprocessing="none",
        evaluate=True,
    )


def build_markdown_report(
    *,
    request: EstimationRequest,
    settings: Settings,
    assessment_surface: str,
    prelude: StructuredPrelude,
    rendered: RenderedPrompt,
    bundle_version: str,
) -> str:
    messages = [
        {"role": "system", "content": rendered.system_prompt},
        {"role": "user", "content": rendered.user_prompt},
    ]
    if settings.openai_api_key.strip():
        model_hint = settings.openai_litellm_model_id()
    elif settings.anthropic_api_key.strip():
        model_hint = settings.anthropic_litellm_model_id()
    else:
        model_hint = "(set OPENAI_API_KEY or ANTHROPIC_API_KEY for model id)"

    preprocessed_note = (
        prelude.preprocessed_markdown_for_template.strip()
        if prelude.preprocessed_markdown_for_template
        else ""
    )

    lines = [
        "# Estimation v2 — LLM prompt dump (dry run)",
        "",
        "## Run metadata",
        f"- Generated (UTC): {datetime.now(UTC).isoformat()}",
        f"- Prompt bundle label: `estimation/{bundle_version}`",
        f"- `prompt_version` (rendered): `{rendered.prompt_version}`",
        f"- `examples_version`: `{rendered.examples_version}`",
        f"- Preprocessing: `{request.preprocessing}`",
        f"- Max output tokens (would send): `{prelude.max_output_tokens}`",
        f"- Model (from settings): `{model_hint}`",
        f"- Structured response schema: `{DomainEstimationResult.__name__}`",
        f"- Jinja templates: `{', '.join(rendered.template_names)}`",
        "",
        "## Pipeline context (not sent as chat messages)",
        "",
        "Assessment surface (guardrails):",
        "",
        "```text",
        assessment_surface.strip(),
        "```",
        "",
    ]
    if preprocessed_note:
        lines.extend(
            [
                "Two-phase preprocessed user body (replaces guided form in user message):",
                "",
                "```markdown",
                preprocessed_note,
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## LLM messages (exact payload shape)",
            "",
            "Instructor → LiteLLM uses this message list:",
            "",
            "```json",
            json.dumps(messages, ensure_ascii=False, indent=2),
            "```",
            "",
            "---",
            "",
            "## Message 1 — role: `system`",
            "",
            rendered.system_prompt,
            "",
            "---",
            "",
            "## Message 2 — role: `user`",
            "",
            rendered.user_prompt,
            "",
            "---",
            "",
            "## Character counts",
            f"- system: {len(rendered.system_prompt)}",
            f"- user: {len(rendered.user_prompt)}",
            f"- total: {len(rendered.system_prompt) + len(rendered.user_prompt)}",
            "",
        ]
    )
    return "\n".join(lines)


async def run_dump(
    *,
    preprocessing: str,
    prompt_version_override: str | None,
) -> Path:
    settings = Settings()
    request = build_full_dummy_request().model_copy(update={"preprocessing": preprocessing})

    assessment_surface = render_estimation_assessment_surface(request, settings=settings)
    service = EstimationService(settings, providers=[])
    prelude = await service.prepare_structured_prelude(
        request,
        assessment_surface=assessment_surface,
        skip_domain_guardrail=True,
    )

    version_override = prompt_version_override or settings.prompt_estimation_version.strip() or None
    bundle_version = version_override.strip() if version_override else resolve_prompt_bundle_version(settings)

    rendered = render_estimation_prompt(
        request,
        examples=load_examples(),
        preprocessing=preprocessing,  # type: ignore[arg-type]
        preprocessed_requirements=prelude.preprocessed_markdown_for_template,
        version=version_override,
        examples_version=EXAMPLES_VERSION,
        settings=settings,
    )

    body = build_markdown_report(
        request=request,
        settings=settings,
        assessment_surface=assessment_surface,
        prelude=prelude,
        rendered=rendered,
        bundle_version=bundle_version,
    )

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    destination = _OUTPUT_DIR / f"prompt-{bundle_version}-{stamp}.md"
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    destination.write_text(body, encoding="utf-8")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dump rendered v2 estimation prompts without the structured LLM call.",
    )
    parser.add_argument(
        "--preprocessing",
        choices=("none", "inline_cleaning", "two_phase"),
        default="none",
        help="Match EstimationRequest.preprocessing; two_phase calls the LLM for extraction.",
    )
    parser.add_argument(
        "--prompt-version",
        default="",
        help="Override PROMPT_ESTIMATION_VERSION (e.g. v2, v1).",
    )
    args = parser.parse_args()
    dest = asyncio.run(
        run_dump(
            preprocessing=args.preprocessing,
            prompt_version_override=args.prompt_version or None,
        )
    )
    print(f"Wrote {dest}")


if __name__ == "__main__":
    main()
