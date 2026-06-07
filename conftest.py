"""Repository-root pytest configuration."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
_TESTS_DIR = _REPO_ROOT / "tests"


def _prefer_root_evals_package() -> None:
    tests_dir = str(_TESTS_DIR)
    repo_root = str(_REPO_ROOT)
    sys.path[:] = [
        repo_root,
        *[entry for entry in sys.path if entry not in {"", repo_root, tests_dir}],
    ]
    for name in list(sys.modules):
        if name != "evals" and not name.startswith("evals."):
            continue
        module_file = getattr(sys.modules[name], "__file__", "") or ""
        if f"{tests_dir}/evals" in module_file.replace("\\", "/"):
            del sys.modules[name]


_prefer_root_evals_package()


def pytest_configure(config) -> None:
    _prefer_root_evals_package()
