#!/usr/bin/env python3
"""Minimal Anthropic Messages API ping using ``proyectos/estimador-cag/.env``.

Uses ``httpx`` (dev dependency, same as ``openai_api_ping.py`` / ``stress_api.py``).

Examples (from ``proyectos/estimador-cag``)::

    uv run python dev-tools/anthropic_api_ping.py

Prints the JSON body and a trailing ``HTTP_STATUS:<code>`` line.

Anthropic requires the ``anthropic-version`` header; override with env
``ANTHROPIC_API_VERSION`` if your account/SDK docs specify another value.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
_DEFAULT_API_VERSION = "2023-06-01"


def main() -> int:
    if not _ENV_FILE.is_file():
        print(f"Missing .env at {_ENV_FILE}", file=sys.stderr)
        return 1

    load_dotenv(_ENV_FILE)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("ANTHROPIC_API_KEY is empty in .env", file=sys.stderr)
        return 1

    model = (os.environ.get("ANTHROPIC_MODEL") or "claude-haiku-4-5-20251001").strip() or "claude-haiku-4-5-20251001"
    api_version = (
        os.environ.get("ANTHROPIC_API_VERSION") or _DEFAULT_API_VERSION
    ).strip() or _DEFAULT_API_VERSION

    payload = {
        "model": model,
        "max_tokens": 256,
        "system": "Reply briefly.",
        "messages": [
            {"role": "user", "content": "Say hello in Spanish in one short sentence."},
        ],
    }

    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            _MESSAGES_URL,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": api_version,
            },
            json=payload,
        )

    print(response.text)
    print(f"HTTP_STATUS:{response.status_code}")
    return 0 if response.is_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
