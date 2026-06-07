"""Render versioned Actor-Critic-Boss Jinja2 prompts."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.schemas.acb.critic import CriticFeedback
from app.schemas.estimation_result import EstimationResult
from app.services.prompt_renderer import PromptRenderer
from app.services.prompt_versions import PROMPTS_ROOT

ACB_PROMPT_VERSION = "acb/v1"
_ACB_USE_CASE = "acb"
_ACB_VERSION = "v1"


@dataclass(frozen=True)
class AcbRenderedRolePrompt:
    """System and user prompts for one ACB role."""

    system_prompt: str
    user_prompt: str
    prompt_version: str


@dataclass(frozen=True)
class _AcbTemplateSet:
    actor_system_template: str
    actor_revision_template: str
    critic_system_template: str
    critic_user_template: str
    boss_system_template: str
    boss_user_template: str


def _load_acb_template_set(*, prompts_root: Path | None = None) -> _AcbTemplateSet:
    root = prompts_root or PROMPTS_ROOT
    manifest = root / _ACB_USE_CASE / _ACB_VERSION / "manifest.toml"
    raw = tomllib.loads(manifest.read_text(encoding="utf-8"))
    prefix = f"{_ACB_USE_CASE}/{_ACB_VERSION}/"
    return _AcbTemplateSet(
        actor_system_template=prefix + str(raw["actor_system_template"]),
        actor_revision_template=prefix + str(raw["actor_revision_template"]),
        critic_system_template=prefix + str(raw["critic_system_template"]),
        critic_user_template=prefix + str(raw["critic_user_template"]),
        boss_system_template=prefix + str(raw["boss_system_template"]),
        boss_user_template=prefix + str(raw["boss_user_template"]),
    )


def _metadata_dict(project_metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if project_metadata is None:
        return {}
    return {str(k): v for k, v in project_metadata.items()}


def render_acb_actor_prompts(
    *,
    assessment_surface: str,
    project_metadata: Mapping[str, Any] | None,
    revision_instructions: str | None,
    iteration: int = 1,
    prompts_root: Path | None = None,
) -> AcbRenderedRolePrompt:
    renderer = PromptRenderer(prompts_root)
    templates = _load_acb_template_set(prompts_root=prompts_root)
    revision_block = ""
    if revision_instructions and revision_instructions.strip():
        revision_block = renderer.render_partial(
            templates.actor_revision_template,
            {
                "iteration": iteration,
                "revision_instructions": revision_instructions.strip(),
            },
        )
    system_prompt = renderer.render_partial(
        templates.actor_system_template,
        {"revision_block": revision_block},
    )
    user_prompt = assessment_surface.strip()
    return AcbRenderedRolePrompt(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        prompt_version=ACB_PROMPT_VERSION,
    )


def render_acb_critic_prompts(
    *,
    candidate: EstimationResult,
    assessment_surface: str,
    project_metadata: Mapping[str, Any] | None,
    prompts_root: Path | None = None,
) -> AcbRenderedRolePrompt:
    renderer = PromptRenderer(prompts_root)
    templates = _load_acb_template_set(prompts_root=prompts_root)
    ctx = {
        "assessment_surface": assessment_surface.strip(),
        "project_metadata": _metadata_dict(project_metadata),
        "candidate_json": candidate.model_dump_json(indent=2),
    }
    return AcbRenderedRolePrompt(
        system_prompt=renderer.render_partial(templates.critic_system_template, ctx),
        user_prompt=renderer.render_partial(templates.critic_user_template, ctx),
        prompt_version=ACB_PROMPT_VERSION,
    )


def render_acb_boss_prompts(
    *,
    candidate: EstimationResult,
    critic_feedback: CriticFeedback,
    iteration: int,
    max_iterations: int,
    budget_remaining: int,
    prompts_root: Path | None = None,
) -> AcbRenderedRolePrompt:
    renderer = PromptRenderer(prompts_root)
    templates = _load_acb_template_set(prompts_root=prompts_root)
    ctx = {
        "candidate_json": candidate.model_dump_json(indent=2),
        "critic_feedback": critic_feedback,
        "iteration": iteration,
        "max_iterations": max_iterations,
        "budget_remaining": budget_remaining,
    }
    return AcbRenderedRolePrompt(
        system_prompt=renderer.render_partial(templates.boss_system_template, ctx),
        user_prompt=renderer.render_partial(templates.boss_user_template, ctx),
        prompt_version=ACB_PROMPT_VERSION,
    )
