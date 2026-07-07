# ADR-002: Transcript PII ingest scope

## Context

`feature-065` adds optional Presidio-based redaction on **transcript ingest only**. Budget JSON ingest remains unchanged per ADR-001.

## Decision

- PII runs **only** in transcript ingest CLI (`app/scripts/ingest_transcript.py`) when `TRANSCRIPT_PII_ENABLED=true`.
- Default analyzer in fast tests uses `RegexPiiAnalyzer`; Presidio is lazy-imported behind the optional `pii` dependency group.
- No PII processing on live RAG estimate or session chat paths.
- Logs record entity **types** and counts, never raw spans.

## Consequences

- Teaching/demo scope only; not a compliance certification.
- Operators must install `uv sync --group pii` and download a spaCy model for live Presidio.
- Reversible pseudonym maps are deferred; redaction is destructive in persisted chunks.

## Repository commits (master-ia)

- Recorded when feature-065 closes.
