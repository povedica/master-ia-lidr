"""Resolve versioned prompt directories and manifest metadata."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from app.services.prompt_exceptions import PromptTemplateNotFound, PromptVersionError

_APP_DIR = Path(__file__).resolve().parent.parent
PROMPTS_ROOT = _APP_DIR / "prompts"

DEFAULT_PROMPT_VERSIONS: dict[str, str] = {"estimation": "v1"}


@dataclass(frozen=True)
class PromptTemplateSet:
    """Resolved filesystem paths for one prompt bundle."""

    use_case: str
    version: str
    root: Path
    system_template: str
    user_template: str
    examples_template: str


def _manifest_path(use_case: str, version: str) -> Path:
    return PROMPTS_ROOT / use_case / version / "manifest.toml"


def resolve_prompt_template_set(
    use_case: str,
    requested_version: str | None = None,
    *,
    prompts_root: Path | None = None,
) -> PromptTemplateSet:
    """Load ``manifest.toml`` and validate template files exist."""

    root_base = prompts_root or PROMPTS_ROOT
    version = (requested_version or DEFAULT_PROMPT_VERSIONS.get(use_case, "v1")).strip()
    if not version:
        raise PromptVersionError(f"Empty version for use_case={use_case!r}")

    bundle_root = root_base / use_case / version
    manifest_file = bundle_root / "manifest.toml"
    if not manifest_file.is_file():
        raise PromptVersionError(f"No manifest at {manifest_file}")

    raw = tomllib.loads(manifest_file.read_text(encoding="utf-8"))
    try:
        mu = str(raw["use_case"])
        mv = str(raw["version"])
        system_t = str(raw["system_template"])
        user_t = str(raw["user_template"])
        examples_t = str(raw["examples_template"])
    except KeyError as exc:
        raise PromptVersionError(f"manifest.toml missing key: {exc}") from exc

    if mu != use_case or mv != version:
        raise PromptVersionError(
            f"manifest use_case/version mismatch: expected {use_case}/{version}, got {mu}/{mv}"
        )

    rel = f"{use_case}/{version}/"
    paths = [
        (system_t, rel + system_t),
        (user_t, rel + user_t),
        (examples_t, rel + examples_t),
    ]
    for name, rel_path in paths:
        candidate = root_base / rel_path
        if not candidate.is_file():
            raise PromptTemplateNotFound(f"Missing template {name!r} at {candidate}")

    return PromptTemplateSet(
        use_case=use_case,
        version=version,
        root=bundle_root,
        system_template=rel + system_t,
        user_template=rel + user_t,
        examples_template=rel + examples_t,
    )
