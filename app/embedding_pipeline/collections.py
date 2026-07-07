"""Multi-index collection registry and rule-based routing (feature-063)."""

from __future__ import annotations

import re
from enum import StrEnum


class Collection(StrEnum):
    BUDGETS = "budgets"
    TRANSCRIPTS = "transcripts"
    TECHNICAL_DOCS = "technical_docs"


_COLLECTION_RULES: dict[Collection, tuple[str, ...]] = {
    Collection.BUDGETS: (
        r"\bbudget(s)?\b",
        r"\bestimat(e|ed|ion|es)\b",
        r"\bhours?\b",
        r"\bhow much\b",
    ),
    Collection.TRANSCRIPTS: (
        r"\bmeeting(s)?\b",
        r"\btranscript(s)?\b",
        r"\bdiscuss(ed|ion)?\b",
        r"\bkick-?off\b",
    ),
    Collection.TECHNICAL_DOCS: (
        r"\bdocument(ation|s)?\b",
        r"\bspec(ification)?s?\b",
        r"\barchitecture\b",
        r"\brunbook\b",
    ),
}


def match_collections(query_text: str) -> list[Collection]:
    """Return collections whose vocabulary rules match ``query_text`` (registry order)."""

    text = query_text.lower()
    hits: list[Collection] = []
    for collection, patterns in _COLLECTION_RULES.items():
        if any(re.search(pattern, text) for pattern in patterns):
            hits.append(collection)
    return hits


def default_collection() -> Collection:
    return Collection.BUDGETS
