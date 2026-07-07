# Feature: Transcript PII Ingest Optional (Phase 4 parity)

## Objective

Add **optional Presidio-based PII redaction** on transcript ingest only, behind an explicit feature flag and ADR scope approval:

1. Detect PII entities in transcript text before chunking.
2. Pseudonymize or mask spans; optionally persist reversible mapping table for authorized de-anonymization in dev.
3. Wire into transcript ingest path from `feature-063` without affecting budget JSON ingest (ADR-001).

This is **Phase 4 parity** child slice of `docs/work-items/feature-053-official-master-parity-alignment.md` (FR-23).

## Context

### Official reference

| Artifact | Official path | Behavior |
| --- | --- | --- |
| PII analyzer | `ingestion/pii/analyzer.py` | Presidio entity detection |
| Anonymizer | `ingestion/pii/anonymizer.py` | Replace spans with tokens |
| Mappings | `MappingsRepository` | Pseudonym map persistence |

### `master-ia` fork choices

- **Opt-in only** — default off; heavy deps (`presidio-analyzer`, `presidio-anonymizer`, `spacy` model) as **optional** `uv` dependency group `pii`.
- Scope limited to **transcript ingest CLI/API** from `feature-063`; budget path untouched (ADR-001).
- Require **ADR-002** (or amendment to ADR-001) documenting scope before merge if Presidio lands in production path.
- No PII processing in hot RAG estimate path — only at ingest.
- Mappings table optional MVP: in-memory map in dev; Postgres `pii_mappings` only if needed for teaching demo.

### Parent roadmap

- Depends on: `feature-063` transcript parser/ingest path.
- Blocks: none on critical parity path.
- High risk / weight — ship behind `TRANSCRIPT_PII_ENABLED=false`.

## Scope

### Includes

- ADR-002 draft: scope, entities covered, retention, dev vs prod.
- `app/embedding_pipeline/pii/` — thin wrapper over Presidio analyzer + anonymizer.
- Hook in transcript ingest: `redact_transcript(text) -> RedactedTranscript`.
- Settings: `TRANSCRIPT_PII_ENABLED`, `TRANSCRIPT_PII_ENTITIES` (comma list), `TRANSCRIPT_PII_LANGUAGE`.
- Optional Alembic `pii_mappings` table (dev_mode only) — **defer** if ADR says stateless redaction is enough.
- Unit tests with **canned analyzer results** (no real Presidio in fast suite).
- `@pytest.mark.slow` integration test with real Presidio when group installed.
- `.env.example`, README warning about spacy model download.

### Excludes

- Presidio on budget JSON or live estimate requests.
- Pandera / catalog cleaning (ADR-001 deferred).
- GDPR compliance certification — educational scope only.
- Automatic PII detection in session chat (only file ingest).

## Functional Requirements

- **FR-01:** When `TRANSCRIPT_PII_ENABLED=false`, ingest byte-identical to feature-063 path.
- **FR-02:** When enabled, emails and phone numbers in fixture transcript are masked before chunk persistence.
- **FR-03:** Fast tests mock Presidio; no spacy model required for default `uv run pytest`.
- **FR-04:** Logs never emit raw PII spans — only entity types and counts.
- **FR-05:** Optional mappings stored with stable pseudonym tokens (e.g. `<PERSON_1>`).
- **FR-06:** Document one-time setup: `python -m spacy download en_core_web_lg` (or configured model).

## Technical Approach

### Module layout

```text
docs/work-items/adr-002-transcript-pii-ingest-scope.md
app/embedding_pipeline/pii/redactor.py
app/embedding_pipeline/pii/types.py
app/embedding_pipeline/parsers/transcript_txt.py   # hook after read
pyproject.toml                                     # optional group pii
tests/embedding_pipeline/test_pii_redactor.py
```

### Dependency group (optional)

```toml
[dependency-groups.pii]
dependencies = [
  "presidio-analyzer",
  "presidio-anonymizer",
]
```

### Settings preview

```text
TRANSCRIPT_PII_ENABLED=false
TRANSCRIPT_PII_ENTITIES=EMAIL_ADDRESS,PHONE_NUMBER,PERSON
TRANSCRIPT_PII_LANGUAGE=en
```

## Acceptance Criteria

- [ ] **AC-01:** ADR-002 committed with scope and consequences.
- [ ] **AC-02:** Mocked unit test: fixture with email → redacted content in chunk.
- [ ] **AC-03:** Flag off → no import of Presidio in ingest path (lazy import).
- [ ] **AC-04:** Fast suite passes without `pii` group installed.
- [ ] **AC-05:** README documents optional install and spacy model.

## Test Plan

### Unit tests

- Mock analyzer returning canned spans; assert anonymized text.
- Enabled flag gates redactor invocation.

### Slow tests

- `@pytest.mark.slow` with real Presidio on short fixture (opt-in).

### Manual

- Ingest sample transcript with fake emails; verify DB content masked.

## Verification

| Check | Command |
| --- | --- |
| Unit | `uv run pytest tests/embedding_pipeline/test_pii_redactor.py -q` |
| Fast suite | `uv run pytest` |
| Slow | `uv sync --group pii && uv run pytest -m slow tests/embedding_pipeline/test_pii_redactor.py` |

**Not verified yet:** multilingual PII; reversibility audit; production compliance.

## Documentation Plan

| Artifact | Update |
| --- | --- |
| `adr-002-transcript-pii-ingest-scope.md` | Decision record |
| `.env.example` | PII flags (commented optional group) |
| `README.md` | Optional PII install section |

## Implementation Plan

- [ ] **Step 1:** ADR-002 draft + review.
- [ ] **Step 2:** `pii/redactor.py` with injectable analyzer (TDD mocks).
- [ ] **Step 3:** Hook transcript ingest + settings.
- [ ] **Step 4:** Docs + optional dependency group.

## Estimation

- Size: **M**
- Estimated time: **4–5 hours**
- Planned steps: **4**

## Pull Request

- Draft: https://github.com/povedica/master-ia-lidr/pull/58
- Branch: `feature/065-transcript-pii-ingest-optional`

## How to start

```text
/start-task docs/work-items/feature-065-transcript-pii-ingest-optional.md
```

Parent: `docs/work-items/feature-053-official-master-parity-alignment.md` Phase 4.
Prerequisite: `feature-063` transcript ingest merged; ADR-002 approved.
