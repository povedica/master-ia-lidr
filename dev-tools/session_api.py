#!/usr/bin/env python3
"""Create a session and submit a transcript-centered estimate (session API smoke helper).

Uses ``httpx`` (dev dependency, same as ``stress_api.py``).

Examples (from the repository root)::

    uv run uvicorn app.main:app --reload

    # Full flow: create session + estimate (prints JSON responses)
    uv run python dev-tools/session_api.py

    # Only create a session and print the session_id
    uv run python dev-tools/session_api.py --create-only

    # Reuse an existing session for a follow-up turn
    uv run python dev-tools/session_api.py --session-id <uuid> --transcript "Turn 2: add SSO and audit log export."

    # Custom JSON body from file
    uv run python dev-tools/session_api.py --json-file path/to/request.json

Warning: ``POST /api/v1/sessions/{id}/estimate`` triggers real provider work unless mocks
are configured. Transcript must be at least 80 characters after trim.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

_DEFAULT_BASE_URL = "http://127.0.0.1:8000"
_DEFAULT_TRANSCRIPT = (
    "Discovery notes: B2B partners need ticket intake, SSO login, dashboards, "
    "and CSV export for operational reporting. Timeline is flexible for the first release."
)
_DEFAULT_BODY: dict[str, Any] = {
    "project_name": "Partner portal",
    "project_type": "web_saas",
    "transcript": _DEFAULT_TRANSCRIPT,
    "target_audience": "b2b_smb",
    "attachments": [],
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a session and POST /api/v1/sessions/{id}/estimate."
    )
    parser.add_argument(
        "--base-url",
        default=_DEFAULT_BASE_URL,
        help=f"API base URL (default: {_DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Reuse an existing session instead of creating a new one.",
    )
    parser.add_argument(
        "--create-only",
        action="store_true",
        help="Only create a session and print the response; skip estimate.",
    )
    parser.add_argument(
        "--transcript",
        default=None,
        help="Override transcript text (must be >= 80 chars). Other default fields kept on first turn.",
    )
    parser.add_argument(
        "--json-body",
        default=None,
        help="Full SessionEstimateRequest JSON string (overrides --transcript).",
    )
    parser.add_argument(
        "--json-file",
        type=Path,
        default=None,
        help="Path to SessionEstimateRequest JSON file (overrides --json-body and --transcript).",
    )
    parser.add_argument(
        "--get-session",
        action="store_true",
        help="After estimate, also GET /api/v1/sessions/{id} and print the detail response.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Per-request timeout in seconds.",
    )
    return parser.parse_args()


def _load_estimate_body(args: argparse.Namespace) -> dict[str, Any]:
    if args.json_file is not None:
        return json.loads(args.json_file.read_text(encoding="utf-8"))
    if args.json_body is not None:
        return json.loads(args.json_body)
    body = dict(_DEFAULT_BODY)
    if args.transcript is not None:
        body["transcript"] = args.transcript.strip()
    return body


def _print_json(label: str, payload: Any, status_code: int) -> None:
    print(f"=== {label} HTTP {status_code} ===")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print()


def _create_session(client: httpx.Client, base_url: str) -> tuple[str, int]:
    response = client.post(f"{base_url.rstrip('/')}/api/v1/sessions")
    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = {"raw": response.text}
    _print_json("POST /api/v1/sessions", payload, response.status_code)
    if response.status_code != 201:
        raise RuntimeError(f"session create failed with status {response.status_code}")
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise RuntimeError("session create response missing session_id")
    return session_id, response.status_code


def _submit_estimate(
    client: httpx.Client,
    *,
    base_url: str,
    session_id: str,
    body: dict[str, Any],
) -> int:
    response = client.post(
        f"{base_url.rstrip('/')}/api/v1/sessions/{session_id}/estimate",
        json=body,
    )
    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = {"raw": response.text}
    _print_json(f"POST /api/v1/sessions/{session_id}/estimate", payload, response.status_code)
    if response.status_code != 200:
        raise RuntimeError(f"estimate failed with status {response.status_code}")
    return response.status_code


def _get_session(client: httpx.Client, *, base_url: str, session_id: str) -> int:
    response = client.get(f"{base_url.rstrip('/')}/api/v1/sessions/{session_id}")
    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = {"raw": response.text}
    _print_json(f"GET /api/v1/sessions/{session_id}", payload, response.status_code)
    if response.status_code != 200:
        raise RuntimeError(f"session detail failed with status {response.status_code}")
    return response.status_code


def main() -> int:
    args = _parse_args()
    try:
        body = _load_estimate_body(args)
    except (json.JSONDecodeError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.create_only and args.get_session:
        print("error: --create-only cannot be combined with --get-session", file=sys.stderr)
        return 2

    with httpx.Client(timeout=args.timeout) as client:
        if args.session_id:
            session_id = args.session_id.strip()
            print(f"Using existing session_id={session_id}\n")
        else:
            session_id, _ = _create_session(client, args.base_url)

        if args.create_only:
            print(f"session_id={session_id}")
            return 0

        _submit_estimate(client, base_url=args.base_url, session_id=session_id, body=body)
        if args.get_session:
            _get_session(client, base_url=args.base_url, session_id=session_id)

    print(f"session_id={session_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
