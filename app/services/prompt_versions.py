"""Resolve versioned prompt directories and manifest metadata."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.services.estimation_engine import EstimationMode
from app.services.prompt_exceptions import PromptTemplateNotFound, PromptVersionError

_APP_DIR = Path(__file__).resolve().parent.parent
PROMPTS_ROOT = _APP_DIR / "prompts"

DEFAULT_PROMPT_VERSIONS: dict[str, str] = {"estimation": "v2"}

_MODE_PARTIAL_BASENAMES: tuple[str, ...] = tuple(m.value for m in EstimationMode)


@dataclass(frozen=True)
class PromptTemplateSet:
    """Resolved filesystem paths for one prompt bundle."""

    use_case: str
    version: str
    root: Path
    system_template: str
    user_template: str
    examples_template: str
    guided_request_template: str
    assessment_surface_template: str
    structured_output_hint_template: str
    inline_cleaning_template: str
    two_phase_extraction_system_template: str


def resolve_prompt_bundle_version(settings: Settings) -> str:
    """Resolve estimation bundle version from settings.

    Phase 1: ``PROMPT_ESTIMATION_VERSION`` env only (empty → default bundle).
    Phase 2 (future): optional ``PromptBundleSelector`` for tenant/admin/request overrides
    with env as fallback — see feature-016 FR-09.
    """

    override = settings.prompt_estimation_version.strip()
    if override:
        return override
    return DEFAULT_PROMPT_VERSIONS["estimation"]


def _manifest_path(use_case: str, version: str) -> Path:
    return PROMPTS_ROOT / use_case / version / "manifest.toml"


def _rel_template(use_case: str, version: str, name: str) -> str:
    return f"{use_case}/{version}/{name}"


def _require_file(root_base: Path, rel_path: str) -> None:
    candidate = root_base / rel_path
    if not candidate.is_file():
        raise PromptTemplateNotFound(f"Missing template at {candidate}")


def resolve_prompt_template_set(
    use_case: str,
    requested_version: str | None = None,
    *,
    prompts_root: Path | None = None,
) -> PromptTemplateSet:
    """Load ``manifest.toml`` and validate template files exist."""

    root_base = prompts_root or PROMPTS_ROOT
    version = (requested_version or DEFAULT_PROMPT_VERSIONS.get(use_case, "v2")).strip()
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
        guided_t = str(raw["guided_request_template"])
        assessment_t = str(raw["assessment_surface_template"])
        hint_t = str(raw["structured_output_hint_template"])
        inline_t = str(raw["inline_cleaning_template"])
        extraction_t = str(raw["two_phase_extraction_system_template"])
    except KeyError as exc:
        raise PromptVersionError(f"manifest.toml missing key: {exc}") from exc

    if mu != use_case or mv != version:
        raise PromptVersionError(
            f"manifest use_case/version mismatch: expected {use_case}/{version}, got {mu}/{mv}"
        )

    rel = f"{use_case}/{version}/"
    for name in (
        system_t,
        user_t,
        examples_t,
        guided_t,
        assessment_t,
        hint_t,
        inline_t,
        extraction_t,
    ):
        _require_file(root_base, rel + name)

    for mode_name in _MODE_PARTIAL_BASENAMES:
        mode_rel = f"{rel}partials/modes/{mode_name}.md.j2"
        _require_file(root_base, mode_rel)

    return PromptTemplateSet(
        use_case=use_case,
        version=version,
        root=bundle_root,
        system_template=_rel_template(use_case, version, system_t),
        user_template=_rel_template(use_case, version, user_t),
        examples_template=_rel_template(use_case, version, examples_t),
        guided_request_template=_rel_template(use_case, version, guided_t),
        assessment_surface_template=_rel_template(use_case, version, assessment_t),
        structured_output_hint_template=_rel_template(use_case, version, hint_t),
        inline_cleaning_template=_rel_template(use_case, version, inline_t),
        two_phase_extraction_system_template=_rel_template(use_case, version, extraction_t),
    )


def mode_partial_template_path(template_set: PromptTemplateSet, mode: EstimationMode) -> str:
    """Relative template path for a mode fragment under ``app/prompts``."""

    return f"{template_set.use_case}/{template_set.version}/partials/modes/{mode.value}.md.j2"
