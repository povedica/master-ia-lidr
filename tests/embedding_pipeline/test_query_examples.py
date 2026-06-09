"""Unit tests for query_examples script (feature-039)."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

import query_examples


def test_truncate_preview_short_text_unchanged() -> None:
    text = "Short chunk text."
    assert query_examples.truncate_preview(text) == text


def test_truncate_preview_long_text_adds_ellipsis() -> None:
    text = "a" * 150
    preview = query_examples.truncate_preview(text, max_chars=120)
    assert len(preview) == 120
    assert preview.endswith("...")


def test_format_distance_uses_four_decimals() -> None:
    assert query_examples.format_distance(0.231456) == "0.2315"


def test_format_result_line_includes_required_fields() -> None:
    line = query_examples.format_result_line(
        chunk_id=42,
        distance=0.2314,
        chunk_type="budget_component",
        content="Backend service with JWT authentication for mobile banking API.",
    )
    assert "chunk_id=42" in line
    assert "distance=0.2314" in line
    assert "chunk_type=budget_component" in line
    assert "Backend service" in line


def test_build_search_payload_uses_k_five() -> None:
    payload = query_examples.build_search_payload("OAuth backend")
    assert payload == {"query": "OAuth backend", "k": 5}


def test_format_query_section_empty_results() -> None:
    section = query_examples.format_query_section(
        category="Unrelated domain",
        query="Restaurant design",
        results=[],
    )
    assert "Unrelated domain" in section
    assert "Restaurant design" in section
    assert "(no results)" in section


def test_format_query_section_with_results() -> None:
    section = query_examples.format_query_section(
        category="Direct match",
        query="OAuth backend",
        results=[
            {
                "chunk_id": 1,
                "distance": 0.42,
                "chunk_type": "budget_component",
                "content": "OAuth 2.0 authentication backend",
            }
        ],
    )
    assert "Direct match" in section
    assert "chunk_id=1" in section
    assert "distance=0.4200" in section


def test_post_search_parses_success_response() -> None:
    body = json.dumps(
        {
            "query": "test",
            "k": 5,
            "search_time_ms": 10,
            "results": [{"chunk_id": 1, "distance": 0.1}],
        }
    ).encode()

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = body
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    mock_opener = MagicMock(return_value=mock_response)

    result = query_examples.post_search(
        "http://127.0.0.1:8000",
        "test",
        opener=mock_opener,
    )

    assert result["results"][0]["chunk_id"] == 1
    mock_opener.assert_called_once()
    request = mock_opener.call_args[0][0]
    assert request.full_url == "http://127.0.0.1:8000/api/v1/search"
    assert json.loads(request.data.decode()) == {"query": "test", "k": 5}


def test_post_search_raises_on_http_error() -> None:
    mock_response = MagicMock()
    mock_response.status = 500
    mock_response.read.return_value = b'{"detail":"fail"}'
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with pytest.raises(query_examples.SearchApiError, match="HTTP 500"):
        query_examples.post_search(
            "http://127.0.0.1:8000",
            "test",
            opener=MagicMock(return_value=mock_response),
        )


def test_main_exits_nonzero_on_api_error(capsys: pytest.CaptureFixture[str]) -> None:
    with patch(
        "query_examples.post_search",
        side_effect=query_examples.SearchApiError("HTTP 503"),
    ):
        exit_code = query_examples.main(["--base-url", "http://127.0.0.1:8000"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "HTTP 503" in captured.err


def test_main_prints_all_query_categories(capsys: pytest.CaptureFixture[str]) -> None:
    fake_response = {
        "query": "ignored",
        "k": 5,
        "search_time_ms": 1,
        "results": [],
    }

    with patch("query_examples.post_search", return_value=fake_response):
        exit_code = query_examples.main(["--base-url", "http://127.0.0.1:8000"])

    assert exit_code == 0
    captured = capsys.readouterr()
    for category, _query in query_examples.QUERY_EXAMPLES:
        assert category in captured.out
