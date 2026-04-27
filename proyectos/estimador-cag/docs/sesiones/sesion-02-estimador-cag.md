# Sesión 02 — Estimador CAG

## Enlace al feature

- [Feature: configuración inicial CAG](../decisiones/feature-configuracion-inicial-cag.md)

## Avance

Implementación inicial del API en `proyectos/estimador-cag/`: FastAPI, configuración con `pydantic-settings`, ejemplos estáticos en `app/context/examples.py`, servicio OpenAI aislado, `POST /api/v1/estimate`, `GET /health`, tests con `pytest` sin llamadas reales al proveedor.

## Cómo ejecutarlo

Desde la raíz del subproyecto:

```bash
cd proyectos/estimador-cag
uv sync --group dev
uv run uvicorn app.main:app --reload
```

## Commits del repositorio

La tabla canónica de hashes está en el documento del feature (`## Repository commits (master-ia)`).
