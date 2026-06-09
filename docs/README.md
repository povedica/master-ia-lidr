# Estimador CAG

## Propósito

Documentar el proyecto `estimador-cag`, un ejercicio de AI Engineering para construir un estimador de software con FastAPI, `uv` y Context-Augmented Generation.

## Estructura documental

- `sesiones/`: seguimiento por sesión del máster.
- `decisiones/`: decisiones técnicas y features canónicas.
- `aprendizajes/`: conceptos reutilizables aprendidos durante el proyecto.
- `retrospectivas/`: cierres de hitos o sesiones largas.
- `technical/`: base technical documentation for the project (English), as an extension of the subproject `README.md`. Includes [Postgres pgvector baseline (§22)](technical/README.md#22-postgres-pgvector-baseline-feature-036) and [semantic search endpoint (§23)](technical/README.md#23-semantic-search-endpoint-feature-038).

## Convenciones

- Las notas de aprendizaje se escriben en español.
- Todo el contenido bajo `technical/` (réplica: `docs/technical/`) se escribe en **inglés**.
- Los nombres técnicos, rutas, comandos, modelos y variables se mantienen en inglés.
- No se documentan secretos reales ni valores de `.env`.
- Las decisiones relevantes deben explicar contexto, alternativa elegida y motivo.

## Código y README operativo (repositorio master-ia)

La implementación vive en `proyectos/estimador-cag/`: FastAPI, CAG con ejemplos few-shot cargados desde `app/context/examples/sample-standard-*.txt` (muestreo aleatorio en `app/context/examples.py`), prompts por modo bajo `app/context/prompts/`, y persistencia opcional de la estimación en `output-responses/` cuando `ESTIMATION_OUTPUT_PERSIST_ENABLED=true`.

Para comandos, contrato HTTP y variables de entorno, usa el **`README.md` del subproyecto en git** (inglés) y la extensión **`technical/README.md`** (inglés, réplica bajo `docs/technical/` tras `bash scripts/sync-estimador-cag-docs.sh`).

## Sesión activa

- `sesiones/sesion-02-estimador-cag.md`
- Embedding pipeline / búsqueda semántica:
  - `learnings/docs/sesiones/sesion-07-semantic-search-postgres-baseline.md` (feature-036)
  - `learnings/docs/sesiones/sesion-07-semantic-search-endpoint.md` (feature-038)
