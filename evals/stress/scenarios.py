"""Deterministic multi-turn stress scenarios for session estimation."""

from __future__ import annotations

from dataclasses import dataclass

_TRANSCRIPT_MIN = 80
_SUPPORTED_TURN_COUNTS = (1, 3, 6, 10, 20)
_SCENARIO_NAMES = ("growing", "pivot", "contradiction")


@dataclass(frozen=True)
class TurnSpec:
    turn_index: int
    transcript: str
    fact_to_remember: str


@dataclass(frozen=True)
class StressScenario:
    scenario_name: str
    turns: list[TurnSpec]


def build_scenario(name: str, n_turns: int) -> StressScenario:
    """Build a deterministic scenario with exactly ``n_turns`` conversational turns."""

    normalized = name.strip().lower()
    if normalized not in _SCENARIO_NAMES:
        raise ValueError(f"unsupported scenario: {name}")
    if n_turns not in _SUPPORTED_TURN_COUNTS:
        raise ValueError(f"unsupported turn count: {n_turns}")

    builders = {
        "growing": _build_growing_turns,
        "pivot": _build_pivot_turns,
        "contradiction": _build_contradiction_turns,
    }
    turns = builders[normalized](n_turns)
    return StressScenario(scenario_name=normalized, turns=turns)


def list_supported_turn_counts() -> tuple[int, ...]:
    return _SUPPORTED_TURN_COUNTS


def _pad_transcript(core: str) -> str:
    text = core.strip()
    if len(text) >= _TRANSCRIPT_MIN:
        return text
    filler = " Additional discovery context for stress testing."
    while len(text) < _TRANSCRIPT_MIN:
        text += filler
    return text[:_TRANSCRIPT_MAX] if len(text) > _TRANSCRIPT_MAX else text


_TRANSCRIPT_MAX = 24_000


def _build_growing_turns(n_turns: int) -> list[TurnSpec]:
    increments = [
        ("authentication with SSO", "project name: Nimbus"),
        ("multi-tenant organization model", "auth requirement: SSO mandatory"),
        ("audit log with export to CSV", "feature: audit log export"),
        ("role-based access control", "feature: RBAC"),
        ("billing integration with Stripe", "integration: Stripe billing"),
        ("observability dashboards", "feature: observability dashboards"),
        ("data retention policy controls", "policy: 12 month retention"),
        ("disaster recovery runbooks", "requirement: DR runbooks"),
        ("performance SLO monitoring", "SLO: P95 under 400ms"),
        ("customer onboarding wizard", "feature: onboarding wizard"),
        ("admin impersonation safeguards", "safeguard: admin impersonation audit"),
        ("API rate limiting per tenant", "limit: per-tenant API rate limits"),
        ("webhook delivery retries", "feature: webhook retries"),
        ("feature flag management", "feature: feature flags"),
        ("compliance reporting pack", "compliance: SOC2 reporting pack"),
        ("mobile push notifications", "feature: mobile push"),
        ("search indexing pipeline", "feature: search indexing"),
        ("workflow automation builder", "feature: workflow builder"),
        ("customer success health scoring", "metric: customer health score"),
        ("enterprise support escalation matrix", "process: enterprise escalation matrix"),
    ]
    turns: list[TurnSpec] = []
    for index in range(1, n_turns + 1):
        label, fact = increments[(index - 1) % len(increments)]
        if index == 1:
            core = (
                "We are scoping Nimbus, a B2B SaaS platform for operations teams. "
                f"Initial focus: {label}. "
                "The first release must stay maintainable and measurable."
            )
        else:
            core = (
                f"Turn {index}: extend Nimbus scope with {label}. "
                "Keep prior requirements intact and update the agreed scope summary."
            )
        turns.append(
            TurnSpec(
                turn_index=index,
                transcript=_pad_transcript(core),
                fact_to_remember=fact,
            )
        )
    return turns


def _build_pivot_turns(n_turns: int) -> list[TurnSpec]:
    turns: list[TurnSpec] = []
    for index in range(1, n_turns + 1):
        if index == 1:
            core = (
                "Project Atlas starts as a React + Node web SaaS for logistics coordinators. "
                "We need a credible MVP estimate with clear technology assumptions."
            )
            fact = "stack includes React"
        elif index <= max(2, n_turns // 2):
            core = (
                f"Turn {index}: continue Atlas on React with map visualizations and shipment tracking. "
                "Preserve the original web-first delivery plan."
            )
            fact = "stack includes React"
        else:
            core = (
                f"Turn {index}: pivot Atlas to Flutter mobile-first with offline sync for drivers. "
                "Deprecate the React web client except an admin portal."
            )
            fact = "stack includes Flutter"
        turns.append(
            TurnSpec(
                turn_index=index,
                transcript=_pad_transcript(core),
                fact_to_remember=fact,
            )
        )
    return turns


def _build_contradiction_turns(n_turns: int) -> list[TurnSpec]:
    turns: list[TurnSpec] = []
    for index in range(1, n_turns + 1):
        if index == 1:
            core = (
                "Project Harbor is a compliance portal. Initial budget is fixed and must be respected "
                "throughout discovery."
            )
            fact = "budget locked: 30000 EUR"
        elif index <= max(2, n_turns // 3):
            core = (
                f"Turn {index}: Harbor adds reporting modules while keeping the budget locked at 30000 EUR."
            )
            fact = "budget locked: 30000 EUR"
        else:
            core = (
                f"Turn {index}: leadership increases Harbor budget to 80000 EUR for accelerated delivery. "
                "Treat the higher budget as the new constraint."
            )
            fact = "budget locked: 80000 EUR"
        turns.append(
            TurnSpec(
                turn_index=index,
                transcript=_pad_transcript(core),
                fact_to_remember=fact,
            )
        )
    return turns
