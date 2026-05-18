"""Strict Jinja2 rendering for versioned prompts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError

from app.services.prompt_exceptions import PromptRenderError
from app.services.prompt_versions import PROMPTS_ROOT, PromptTemplateSet


@dataclass(frozen=True)
class RenderedPrompt:
    """Rendered system and user prompts plus artifact metadata."""

    system_prompt: str
    user_prompt: str
    prompt_version: str
    examples_version: str
    template_names: tuple[str, ...]


class PromptRenderer:
    """Owns one Jinja2 environment rooted at ``app/prompts``."""

    def __init__(self, prompts_root: Path | None = None) -> None:
        root = prompts_root or PROMPTS_ROOT
        self._root = root
        self._env = Environment(
            loader=FileSystemLoader(str(root)),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            autoescape=False,
        )

    def render_partial(self, template_path: str, context: Mapping[str, Any]) -> str:
        """Render a single template path relative to ``app/prompts``."""

        try:
            template = self._env.get_template(template_path)
            return template.render(**context).strip()
        except TemplateError as exc:
            raise PromptRenderError(str(exc)) from exc

    def render(
        self,
        template_set: PromptTemplateSet,
        context: Mapping[str, Any],
        *,
        examples_version: str,
    ) -> RenderedPrompt:
        """Render ``examples`` then ``system`` then ``user`` templates."""

        try:
            examples_t = self._env.get_template(template_set.examples_template)
            examples_block = examples_t.render(**context).strip()

            system_ctx = dict(context)
            system_ctx["examples_block"] = examples_block
            system_t = self._env.get_template(template_set.system_template)
            system_prompt = system_t.render(**system_ctx).strip()

            user_t = self._env.get_template(template_set.user_template)
            user_prompt = user_t.render(**context).strip()
        except TemplateError as exc:
            raise PromptRenderError(str(exc)) from exc

        pv = f"{template_set.use_case}/{template_set.version}"
        names = (
            template_set.examples_template.split("/")[-1],
            template_set.system_template.split("/")[-1],
            template_set.user_template.split("/")[-1],
        )
        return RenderedPrompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            prompt_version=pv,
            examples_version=examples_version,
            template_names=names,
        )
