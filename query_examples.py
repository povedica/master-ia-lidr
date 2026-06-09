#!/usr/bin/env python3
"""Exercise POST /api/v1/search with representative query categories (feature-039)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

DEFAULT_API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
SEARCH_PATH = "/api/v1/search"
CONTENT_PREVIEW_CHARS = 120

QUERY_EXAMPLES: list[tuple[str, str]] = [
    (
        "Direct known component",
        "OAuth 2.0 authentication backend with JWT tokens for fintech mobile app",
    ),
    (
        "Semantic reformulation",
        "Authorization service for a banking application",
    ),
    (
        "Unrelated domain",
        "Restaurant interior design and kitchen equipment procurement",
    ),
    (
        "Short/ambiguous query",
        "Backend services",
    ),
    (
        "Specific technical query",
        "FastAPI PostgreSQL migration with async SQLAlchemy and API integration",
    ),
]


class SearchApiError(Exception):
    """Raised when the search endpoint returns a non-success HTTP status."""


def truncate_preview(content: str, max_chars: int = CONTENT_PREVIEW_CHARS) -> str:
    """Return a single-line preview of chunk content."""
    normalized = " ".join(content.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3] + "..."


def format_distance(distance: float) -> str:
    """Format cosine distance with four decimal places."""
    return f"{distance:.4f}"


def format_result_line(
    *,
    chunk_id: int,
    distance: float,
    chunk_type: str,
    content: str,
) -> str:
    """Format one search hit as a concise terminal line."""
    preview = truncate_preview(content)
    return (
        f"  chunk_id={chunk_id}  distance={format_distance(distance)}  "
        f"chunk_type={chunk_type}  content={preview!r}"
    )


def build_search_payload(query: str, k: int = 5) -> dict[str, Any]:
    """Build the JSON body for POST /api/v1/search."""
    return {"query": query, "k": k}


def format_query_section(
    *,
    category: str,
    query: str,
    results: list[dict[str, Any]],
) -> str:
    """Format one query block for terminal or file output."""
    lines = [
        f"=== {category} ===",
        f"Query: {query}",
    ]
    if not results:
        lines.append("(no results)")
    else:
        for result in results:
            lines.append(
                format_result_line(
                    chunk_id=int(result["chunk_id"]),
                    distance=float(result["distance"]),
                    chunk_type=str(result.get("chunk_type", "")),
                    content=str(result.get("content", "")),
                )
            )
    return "\n".join(lines)


def post_search(
    base_url: str,
    query: str,
    *,
    k: int = 5,
    timeout: float = 120.0,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """POST to /api/v1/search and return the parsed JSON body."""
    url = base_url.rstrip("/") + SEARCH_PATH
    payload = json.dumps(build_search_payload(query, k=k)).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urlopen = opener or urllib.request.urlopen
    try:
        with urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            body = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read()

    if status >= 400:
        detail = body.decode("utf-8", errors="replace")[:200]
        raise SearchApiError(f"HTTP {status}: {detail}")

    return json.loads(body.decode("utf-8"))


def run_queries(
    base_url: str,
    *,
    output: Callable[[str], None] | None = None,
    opener: Callable[..., Any] | None = None,
) -> list[tuple[str, str, list[dict[str, Any]]]]:
    """Run all query categories and return collected results."""
    write = output or print
    collected: list[tuple[str, str, list[dict[str, Any]]]] = []

    for category, query in QUERY_EXAMPLES:
        response = post_search(base_url, query, opener=opener)
        results = list(response.get("results", []))
        section = format_query_section(
            category=category,
            query=query,
            results=results,
        )
        write(section)
        write("")
        collected.append((category, query, results))

    return collected


def format_run_header(command: str) -> str:
    """Return a short header describing how the script was invoked."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return textwrap.dedent(
        f"""\
        Command: {command}
        Timestamp: {timestamp}
        API: POST /api/v1/search (k=5)

        """
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run representative semantic search queries against the API.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_API_BASE_URL,
        help=f"API base URL (default: {DEFAULT_API_BASE_URL} or API_BASE_URL env).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    command = " ".join(["python", "query_examples.py", *([] if argv is None else argv)])
    print(format_run_header(command), end="")

    try:
        run_queries(args.base_url)
    except SearchApiError as exc:
        print(f"Search API error: {exc}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Connection error: {exc.reason}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON response: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
