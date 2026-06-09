"""Loader → parser → chunker chain test (feature-035)."""

from __future__ import annotations

from pathlib import Path

from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.loaders.filesystem import FileSystemLoader
from app.embedding_pipeline.parsers.registry import get_parser

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "budget_files"


def test_loader_parser_chunker_produces_expected_component_count() -> None:
    parser = get_parser("json")
    chunker = JSONStructuralChunker(embedding_model="text-embedding-3-small")

    budgets = [parser(path) for path in FileSystemLoader.iter_budget_files(FIXTURES_DIR)]
    chunks = chunker.chunk(budgets)

    assert len(budgets) == 13
    assert len(chunks) == 24
    assert all("::" in chunk.chunk_id for chunk in chunks)
