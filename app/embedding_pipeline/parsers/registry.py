"""Minimal parser registry for upstream budget formats."""

from __future__ import annotations

from app.embedding_pipeline.parsers.budget_json import parse_budget_file
from app.embedding_pipeline.parsers.protocol import BudgetParser

_PARSERS: dict[str, BudgetParser] = {
    "json": parse_budget_file,
}


def get_parser(format_name: str) -> BudgetParser:
    parser = _PARSERS.get(format_name)
    if parser is None:
        supported = ", ".join(sorted(_PARSERS))
        raise KeyError(f"Unsupported budget parser '{format_name}'. Supported: {supported}")
    return parser
