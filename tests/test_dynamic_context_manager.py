"""Unit tests for ``DynamicContextManager``."""

from __future__ import annotations

from app.config import Settings
from app.services.document_extractor import ExtractedAttachment
from app.services.dynamic_context_manager import DynamicContextManager


def test_build_context_block_empty_when_no_text() -> None:
    manager = DynamicContextManager(Settings(openai_api_key="test"))
    assert manager.build_context_block([]) == ""


def test_build_context_block_wraps_attachments() -> None:
    manager = DynamicContextManager(Settings(openai_api_key="test"))
    block = manager.build_context_block(
        [
            ExtractedAttachment(
                filename="spec.pdf",
                content_type="application/pdf",
                text="PDF body here.",
            )
        ]
    )
    assert block.startswith("<attachments>")
    assert 'filename="spec.pdf"' in block
    assert "PDF body here." in block
    assert block.endswith("</attachments>")


def test_build_context_block_truncates_to_budget() -> None:
    manager = DynamicContextManager(
        Settings(openai_api_key="test", max_attachment_context_chars=1024)
    )
    long_text = "x" * 5000
    block = manager.build_context_block(
        [
            ExtractedAttachment(
                filename="big.txt",
                content_type="text/plain",
                text=long_text,
            )
        ]
    )
    assert len(block) <= 1024
    assert "truncated" in block
