# Sesión 12 — Bucle agentic de estimación

## Objetivo

Construir un **bucle agentic explícito** (sin framework) sobre la OpenAI Responses API: el modelo descompone una transcripción, llama herramientas (`search_budgets`, `calculate_estimate`, `validate_estimate`) y devuelve estimación + traza auditable.

## Qué quedó en `master-ia`

| Pieza | Ubicación |
| --- | --- |
| Schemas y traza | `app/services/agentic/agent_schemas.py` |
| Tools + schemas Responses | `app/services/agentic/agent_tools.py` |
| Adapter retrieval | `app/services/agentic/retrieval_adapter.py` |
| Bucle manual | `app/services/agentic/agent_loop.py` |
| CLI entregable | `app/scripts/run_agent_s12.py` |
| API opcional | `POST /api/v1/estimate/agent` |
| Ejercicio | `exercises/session-12/` |

## Decisiones de fork

1. **Responses API directa** — no LiteLLM/Instructor en el bucle (visibilidad pedagógica).
2. **Logging stdlib** — sin `structlog`.
3. **Retrieval** — `search_budgets` envuelve `RetrievalService.retrieve()` de master-ia, no el `retrieve()` del repo oficial.
4. **RAG fijo intacto** — `/api/v1/estimate/rag` sin cambios.

## Comandos útiles

```bash
# Depuración barata (sin DB)
uv run python app/scripts/run_agent_s12.py \
  exercises/session-12/sample_transcript_simple.txt --model gpt-5-mini --stub

# Entregable (API real)
uv run python app/scripts/run_agent_s12.py \
  exercises/session-12/sample_transcript_complex.txt --model gpt-5 --effort medium \
  --out /tmp/agent_trace_complex.txt
```

## Lecciones

- Las **descripciones de tools** son la UI del modelo: invertir tiempo ahí.
- Schemas **planos** en Responses API (`strict: true`, `additionalProperties: false` en cada objeto).
- `previous_response_id` evita bugs de orden con reasoning items en gpt-5.
- Depurar con **gpt-5-mini + stub** antes de gastar en gpt-5 + DB.

## Referencia

- Work item: `docs/work-items/feature-054-agentic-estimation-loop.md`
- Repo oficial: rama `session_12` en `ai-engineering`
