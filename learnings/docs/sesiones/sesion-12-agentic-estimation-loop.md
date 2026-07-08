# Sesión 12 — Bucle agentic de estimación

## Objetivo pedagógico

Demostrar que un **agente no es magia**: es un bucle que tú controlas — el modelo **decide**, ejecutas **tools**, devuelves **observaciones**, y paras cuando toca (con tope de iteraciones).

## Qué quedó en `master-ia`

| Pieza | Ubicación |
| --- | --- |
| Schemas y traza | `app/services/agentic/agent_schemas.py` |
| Tools + schemas Responses | `app/services/agentic/agent_tools.py` |
| Adapter retrieval | `app/services/agentic/retrieval_adapter.py` |
| Bucle manual | `app/services/agentic/agent_loop.py` |
| Cliente OpenAI | `app/services/agentic/openai_client.py` |
| API HTTP | `POST /api/v1/estimate/agent` |
| CLI entregable | `app/scripts/run_agent_s12.py` |
| Ejercicio | `exercises/session-12/` |

## Anatomía del bucle

1. **`responses.create`** con transcripción + `TOOL_SCHEMAS` + `reasoning.summary=auto`.
2. Por cada `function_call` en `response.output`: parsear args → `dispatch_tool` → `function_call_output` con el mismo `call_id`.
3. **`responses.create`** encadenando `previous_response_id` (no reenviar reasoning items a mano).
4. Repetir hasta que no haya más `function_call` o `iterations >= AGENT_MAX_ITERATIONS`.
5. **`responses.parse`** con `text_format=AgentEstimate` para la estimación final estructurada.

La traza (`AgentTrace.render()`) es el entregable pedagógico: **reasoning + action + observation** por paso.

## Decisiones de fork (no “arreglar” sin ADR)

1. **Responses API directa** — el resto del repo usa LiteLLM/Instructor; aquí la visibilidad del bucle es el objetivo.
2. **Logging stdlib** — sin `structlog` (convención master-ia desde feature-052).
3. **Retrieval** — `search_budgets` envuelve `RetrievalService.retrieve()` de master-ia.
4. **Superficie aditiva** — `/api/v1/estimate/rag` y CAG v2 intactos.
5. **`AgentEstimate` ligero** — sin auditoría de citas al estilo S11; el ejercicio es el loop, no la verificación profunda.

## Diseño de tools

- Schemas **planos** Responses API (`strict: true`, `additionalProperties: false`).
- **`search_budgets`**: una búsqueda por componente; queries focalizadas.
- **`calculate_estimate`**: mediana + 15% contingencia; sin referencias → `unbudgeted`, 0h.
- **`validate_estimate`**: guardrails antes de la respuesta final.

> La calidad de las **descripciones** de las tools es la UI del modelo.

## Comandos

```bash
# Depuración barata (sin DB)
uv run python app/scripts/run_agent_s12.py \
  exercises/session-12/sample_transcript_simple.txt --model gpt-5-mini --stub

# Entregable (API real, coste)
uv run python app/scripts/run_agent_s12.py \
  exercises/session-12/sample_transcript_complex.txt --model gpt-5 --effort medium \
  --out /tmp/agent_trace_complex.txt
```

## Disciplina de coste

1. `gpt-5-mini` + transcripción simple + `--stub` → validar mecánica del bucle.
2. `gpt-5` + `medium` + transcripción compleja → entregable para Lia.

## Tests (sin API key en CI)

```bash
uv run pytest tests/test_agent_*.py tests/test_retrieval_adapter.py -q
```

## Documentación técnica

- Referencia completa: [docs/technical/agentic-estimation-loop.md](../../../docs/technical/agentic-estimation-loop.md)
- Work item: [feature-054-agentic-estimation-loop.md](../../../docs/work-items/feature-054-agentic-estimation-loop.md)
- Repo oficial: rama `session_12` en `ai-engineering`

## Pendiente manual

- [ ] AC-10: run con `gpt-5` sobre `sample_transcript_complex.txt` y guardar traza local (no commitear).
