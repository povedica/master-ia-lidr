# Estimador CAG

## Propósito

Documentar el proyecto `estimador-cag`, un ejercicio de AI Engineering para construir un estimador de software con FastAPI, `uv` y Context-Augmented Generation.

## Estructura documental

- **Sesiones (réplica en git):** `learnings/docs/sesiones/` (sincronizar con `bash scripts/sync-estimador-cag-docs.sh`).
- **Aprendizajes (réplica en git):** `learnings/aprendizajes/`.
- **Retrospectivas (réplica en git):** `learnings/retrospectiva/` (origen en el vault: `retrospectivas/`).
- `work-items/`, `examples/`: réplica bajo `docs/` desde el vault del proyecto.
- `technical/`: base technical documentation for the project (English), as an extension of the root `README.md`.

## Convenciones

- Las notas de aprendizaje se escriben en español.
- Todo el contenido bajo `technical/` (réplica: `docs/technical/`) se escribe en **inglés**.
- Los nombres técnicos, rutas, comandos, modelos y variables se mantienen en inglés.
- No se documentan secretos reales ni valores de `.env`.
- Las decisiones relevantes deben explicar contexto, alternativa elegida y motivo.

## Código y README operativo (repositorio master-ia)

La implementación vive en la **raíz del repositorio git `master-ia`**: FastAPI, CAG con ejemplos few-shot cargados desde `app/context/examples/sample-standard-*.txt` (muestreo aleatorio en `app/context/examples.py`), prompts por modo bajo `app/context/prompts/`, y persistencia opcional de la estimación en `output-responses/` cuando `ESTIMATION_OUTPUT_PERSIST_ENABLED=true`.

Para comandos, contrato HTTP y variables de entorno, usa el **`README.md` en la raíz del repositorio** (inglés) y la extensión **`technical/README.md`** (inglés, réplica bajo `docs/technical/` tras `bash scripts/sync-estimador-cag-docs.sh`).

## Sesión activa

- `learnings/docs/sesiones/sesion-02-estimador-cag.md`
