# Sesión 02 — Estimador CAG

## Enlaces

- [Feature: configuración inicial CAG](../../../docs/work-items/feature-configuracion-inicial-cag.md) (arranque del subproyecto).
- [Feature: persistir salidas de estimación (200)](../../../docs/work-items/feature-004-save-estimation-response-output.md) — entrega reciente en repo (`de912b8`).

## Avances y práctica

- **API y CAG:** `POST /api/v1/estimate`, modo adaptativo (`basic` / `standard` / `professional` / `expert_review`), prompts en `app/context/prompts/*.txt`, cadena de proveedores y fallback estático documentados en `README.md` y en `docs/technical/README.md` (réplica versionada).
- **Persistencia opcional de respuestas:** variable `ESTIMATION_OUTPUT_PERSIST_ENABLED`; en `200` escribe `output-responses/response-YYYYmmdd-hhmmss.md` con el texto de `estimation`; fallo de escritura → `503` controlado y log estructurado (ver work item feature-004).
- **Few-shot desde archivos:** el pool vive en `app/context/examples/sample-standard-*.txt`; `load_examples()` en `app/context/examples.py` elige aleatoriamente entre 2 y 4 ejemplos por petición (`EXAMPLES_VERSION = file-random-v2` en código).
- **Documentación técnica (inglés):** `technical/README.md` alineado con layout, variables de entorno, CAG, logging y manejo de errores actuales.
- **Flujo Cursor (repo):** comandos `start-task`, `testing` y `finish-task` refuerzan plan previo a código, TDD cuando aplica y bloques **Verified / Not verified / Residual risk**; regla `14-mode-and-permission-discipline.mdc` para respetar modo Agent/Plan/Ask/Debug; ajuste en `13-babysteps-principle.mdc` para follow-ups fuera de alcance. *Estos cambios de `.cursor/` pueden estar pendientes de commit hasta que ejecutes `/commit-pending`.*

## Decisiones técnicas

- Trazabilidad de contexto: versionado explícito `prompt_version` / `examples_version` en respuestas con `DEV_MODE=true`; al pasar a ejemplos en fichero + muestreo aleatorio, sube la importancia de `examples_version` para correlacionar comportamiento.
- Persistencia solo en disco y solo en éxito, sin base de datos, acorde al alcance de feature-004.

## Verificación (referencia)

- En la última iteración documentada en feature-004: `uv run pytest` sobre los tests citados en ese work item pasó (43 tests en el alcance ampliado allí descrito). Vuelve a ejecutar el subconjunto relevante tras cambios locales.

## Commits del repositorio (master-ia)

La tabla canónica de hashes del feature de persistencia y ejemplos aleatorios está en [feature-004-save-estimation-response-output.md](../../../docs/work-items/feature-004-save-estimation-response-output.md) (`## Repository commits (master-ia)`).

## Dudas / seguimiento

- Renombrado / reorganización de fixtures YAML bajo `api-collection/Estimador CAG/estimations/` (p. ej. `Detail` / `Small` / `Medium` / `Large`): si sigue en el árbol de trabajo sin commit, cerrar con un commit dedicado (`chore` o `docs`) y actualizar la tabla del work item si aplica.
- Tras editar notas en este vault, desde la raíz de **master-ia**: `bash scripts/sync-estimador-cag-docs.sh` para refrescar `docs/` y las carpetas bajo `learnings/` (véase `learnings/README.md`).
