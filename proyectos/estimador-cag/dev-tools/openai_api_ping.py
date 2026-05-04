#!/usr/bin/env python3
"""Minimal OpenAI Chat Completions ping using ``proyectos/estimador-cag/.env``.

Uses ``httpx`` (dev dependency, same as ``stress_api.py``).

Examples (from ``proyectos/estimador-cag``)::

    uv run python dev-tools/openai_api_ping.py

Prints the JSON body and a trailing ``HTTP_STATUS:<code>`` line (same idea as a curl -w probe).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


def main() -> int:
    if not _ENV_FILE.is_file():
        print(f"Missing .env at {_ENV_FILE}", file=sys.stderr)
        return 1

    load_dotenv(_ENV_FILE)

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("OPENAI_API_KEY is empty in .env", file=sys.stderr)
        return 1

    model = (os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip() or "gpt-4o-mini"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Reply briefly."},
            {"role": "user", "content": "Say hello in Spanish in one short sentence."},
        ],
        "max_completion_tokens": 80,
    }

    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json=payload,
        )

    print(response.text)
    print(f"HTTP_STATUS:{response.status_code}")
    return 0 if response.is_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
