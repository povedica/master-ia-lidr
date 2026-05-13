"""Prompt version resolution."""

import pytest

from app.services.prompt_exceptions import PromptTemplateNotFound, PromptVersionError
from app.services.prompt_versions import resolve_prompt_template_set


def test_resolve_v1_estimation_prompt_set() -> None:
    ts = resolve_prompt_template_set("estimation", "v1")
    assert ts.version == "v1"
    assert "estimation/v1/system.j2" == ts.system_template


def test_resolve_unknown_version_raises() -> None:
    with pytest.raises(PromptVersionError):
        resolve_prompt_template_set("estimation", "nonexistent-version-xyz")


def test_resolve_missing_use_case_manifest() -> None:
    with pytest.raises(PromptVersionError):
        resolve_prompt_template_set("unknown_use_case", "v1")
