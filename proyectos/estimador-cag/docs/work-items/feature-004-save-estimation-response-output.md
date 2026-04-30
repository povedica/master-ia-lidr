# Feature: Persist Successful Estimation Output Responses

## Objective
Persist the model estimation text returned by `POST /api/v1/estimate` into markdown files under `output-responses/` for successful (`200 OK`) responses, controlled by an environment variable.

## Context
- The current endpoint returns `estimation` in `EstimateResponse` but does not write any output file.
- The repository already contains an `output-responses/` folder with manually generated response files.
- Runtime configuration is centralized in `app/config.py`, and endpoint orchestration is in `app/routers/estimations.py`.
- This feature must not alter existing API payload structure or failure behavior for non-200 responses.

## Scope
### Includes
- Add one new boolean environment setting to enable/disable response file persistence.
- On `200 OK` only, write a markdown file named `output-responses/response-YYYYmmdd-hhmmss.md`.
- File content must be exactly the value returned in the response `estimation` field.
- Ensure target directory exists before writing.
- Add/adjust tests for enabled and disabled behavior.
- Update `.env.example` and `README.md` with the new setting.

### Excludes
- No persistence for `4xx/5xx` responses.
- No change to response schema fields.
- No DB/storage backend; filesystem only.
- No retention/cleanup policy in this feature.

## Functional Requirements
1. **Feature toggle**
   - New env var: `ESTIMATION_OUTPUT_PERSIST_ENABLED` (default `false`).
   - When `false`, endpoint behavior remains unchanged.
2. **Write condition**
   - Persist only when request completes successfully and returns `200`.
3. **Output path and filename**
   - Directory: `output-responses/` at repository root.
   - Filename: `response-YYYYmmdd-hhmmss.md` (UTC timestamp format).
   - Example: `output-responses/response-20260430-154122.md`.
4. **Output content**
   - Persist only the final `estimation` string from the API response.
5. **Failure handling**
   - If writing fails (permissions/path issues), do not expose internals to clients.
   - Keep API safety: return a controlled `503` (or agreed safe error) and log structured context without secrets.

## Technical Approach
- **Settings**
  - Extend `Settings` in `app/config.py` with `estimation_output_persist_enabled: bool = False`.
- **Persistence helper**
  - Add a small helper in `app/services/` (or local router helper if very small) that:
    - Builds UTC timestamp-based filename.
    - Ensures `output-responses/` exists (`Path.mkdir(parents=True, exist_ok=True)`).
    - Writes markdown content with UTF-8 encoding.
- **Router integration**
  - In `create_estimate`, after obtaining `result` and before returning `EstimateResponse`, call persistence logic only when toggle is enabled.
  - Persist the same `result.estimation` value used in response payload.
- **Error and logging**
  - Catch filesystem errors at the persistence boundary.
  - Log structured warning/error with stable keys and no sensitive data.
  - Convert unrecoverable persistence failures to safe API error response.

## Acceptance Criteria
- [x] With `ESTIMATION_OUTPUT_PERSIST_ENABLED=false`, endpoint responses are unchanged and no file is written.
- [x] With `ESTIMATION_OUTPUT_PERSIST_ENABLED=true`, each successful `200` call writes exactly one markdown file in `output-responses/`.
- [x] File names follow `response-YYYYmmdd-hhmmss.md`.
- [x] File content matches the `estimation` value in the returned JSON.
- [x] No output file is created for `422` or `503` responses.
- [x] `.env.example` and `README.md` document the new env var and behavior.
- [x] Tests validate toggle on/off and write behavior.

## Test Plan
- Unit tests:
  - Settings parsing for `ESTIMATION_OUTPUT_PERSIST_ENABLED`.
  - Filename format and path generation helper.
- Integration tests (`tests/test_api.py`):
  - `200` with toggle enabled writes expected file content.
  - `200` with toggle disabled writes no file.
  - Non-200 responses do not create files.
- Manual checks:
  - `cd proyectos/estimador-cag && uv run pytest tests/test_api.py tests/test_config.py`
  - Optional API run and `curl` verification:
    - `uv run uvicorn app.main:app --reload`
    - POST estimate and confirm file appears in `output-responses/`.

## Documentation Plan
- Update `proyectos/estimador-cag/.env.example` with `ESTIMATION_OUTPUT_PERSIST_ENABLED=false`.
- Update `proyectos/estimador-cag/README.md` configuration section with:
  - Purpose of the toggle.
  - Output folder and filename convention.
- If implemented, sync project docs mirror:
  - From repo root: `bash scripts/sync-estimador-cag-docs.sh`

## Baby Steps
1. Add config field and tests for settings parsing.
2. Implement filesystem helper and unit test for filename/content write.
3. Wire helper into `create_estimate` success path behind toggle.
4. Add/update API tests for enabled/disabled and non-200 cases.
5. Update `.env.example` and `README.md`.
6. Run focused test commands and document verification results.

## Repository commits (master-ia)

| Short hash | Message | Scope / summary |
|------------|---------|-----------------|
| `de912b8` | `feat(estimador-cag): persist outputs and randomize few-shot examples` | Added response persistence behind `ESTIMATION_OUTPUT_PERSIST_ENABLED`, file writer service, API wiring, docs/config updates, and migrated few-shot prompt examples to randomized file-based samples with focused tests. |

## Implementation Notes
- Added `estimation_output_persist_enabled` setting in `app/config.py` with default `False`.
- Implemented `app/services/response_output_writer.py` with UTC filename convention `response-YYYYmmdd-hhmmss.md` and safe filesystem error conversion.
- Wired persistence behind toggle in `app/routers/estimations.py` for successful responses only.
- Added tests in `tests/test_response_output_writer.py`, `tests/test_api.py`, and `tests/test_config.py`.
- Updated docs in `.env.example` and `README.md`.
- Same delivery commit (`de912b8`) introduced file-based few-shot pools and `EXAMPLES_VERSION = file-random-v2`; session and `technical/README.md` were refreshed on 2026-04-30 to match runtime behavior.

## Verification Results
- Command: `cd proyectos/estimador-cag && uv run pytest tests/test_config.py tests/test_response_output_writer.py tests/test_api.py`
- Result: `26 passed`.
- Command: `cd proyectos/estimador-cag && uv run pytest tests/test_config.py tests/test_response_output_writer.py tests/test_examples.py tests/test_llm_service.py tests/test_api.py`
- Result: `43 passed`.
