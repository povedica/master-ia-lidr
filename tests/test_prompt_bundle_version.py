"""Prompt bundle version resolution (FR-09)."""

import filecmp

import pytest

from app.config import Settings
from app.services.prompt_versions import PROMPTS_ROOT
from app.services.prompt_exceptions import PromptVersionError
from app.services.prompt_versions import (
    DEFAULT_PROMPT_VERSIONS,
    resolve_prompt_bundle_version,
    resolve_prompt_template_set,
)


def test_default_prompt_versions_estimation_is_v2() -> None:
    assert DEFAULT_PROMPT_VERSIONS["estimation"] == "v2"


def test_empty_env_resolves_v2() -> None:
    settings = Settings(prompt_estimation_version="")
    assert resolve_prompt_bundle_version(settings) == "v2"


def test_explicit_v1_and_v2() -> None:
    assert resolve_prompt_bundle_version(Settings(prompt_estimation_version="v1")) == "v1"
    assert resolve_prompt_bundle_version(Settings(prompt_estimation_version="v2")) == "v2"


def test_resolve_v2_template_set_has_extended_manifest() -> None:
    ts = resolve_prompt_template_set("estimation", "v2")
    assert ts.version == "v2"
    assert ts.guided_request_template.endswith("guided_request.md.j2")


def test_invalid_version_raises() -> None:
    with pytest.raises(PromptVersionError):
        resolve_prompt_template_set("estimation", "nonexistent-version-xyz")


def test_v1_tree_matches_v2_except_manifest_version_label() -> None:
    v1 = PROMPTS_ROOT / "estimation" / "v1"
    v2 = PROMPTS_ROOT / "estimation" / "v2"
    assert v1.is_dir() and v2.is_dir()
    cmp = filecmp.dircmp(v1, v2)
    assert not cmp.left_only and not cmp.right_only
    diff_files = {name for name in cmp.diff_files if name != "manifest.toml"}
    assert not diff_files
    v1_manifest = (v1 / "manifest.toml").read_text(encoding="utf-8")
    v2_manifest = (v2 / "manifest.toml").read_text(encoding="utf-8")
    assert 'version = "v1"' in v1_manifest
    assert 'version = "v2"' in v2_manifest
    assert v1_manifest.replace('version = "v1"', 'version = "v2"') == v2_manifest
