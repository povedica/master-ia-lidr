# Master IA

Repositorio de trabajo para el **Máster en Inteligencia Artificial**: código, entorno reproducible con Docker y notas enlazadas al Second Brain.

## Second Brain (enlace simbólico)

En la raíz del repo hay un enlace **`second-brain-master-ia`** que apunta a la carpeta del máster dentro de Obsidian / Second Brain:

`/Users/pablo.poveda/CodeProjects/ticktick/docs/second-brain/03 Projects/Trabajo/Master IA`

- Ese contenido **no** se versiona aquí: solo es un acceso rápido desde este proyecto.
- En otra máquina el enlace puede quedar roto hasta que exista la misma ruta o lo recrees con `ln -s`.

## Requisitos en el Mac (host)

- [Docker](https://docs.docker.com/get-docker/) con plugin **Compose v2**.
- **Git**.
- **uv en el host es opcional.** La referencia de versiones es la imagen Docker (uv + Python 3.11 + dependencias del `uv.lock`). Si quieres `uv` también en el terminal del Mac: [Instalación de uv](https://docs.astral.sh/uv/getting-started/installation/).

## Desarrollo con Docker

Desde la raíz del repositorio:

```bash
docker compose build
docker compose up
```

La API queda en `http://localhost:8000`. Documentación interactiva: `http://localhost:8000/docs`.

Para probar la demo de **OpenAI** (`POST /llm/demo`) desde Docker, exporta la clave en el host antes de `docker compose up` (Compose la inyecta en el contenedor):

```bash
export OPENAI_API_KEY="sk-..."
docker compose up
```

Para una shell interactiva dentro del contenedor (útil para pruebas y el checklist de uv):

```bash
docker compose run --rm app bash
```

El arranque ejecuta `uv sync --frozen` para alinear el entorno con `uv.lock`. El directorio `.venv` del contenedor se guarda en el volumen `master_ia_venv` (no se mezcla con un `.venv` del Mac).

## uv y Python (dentro del contenedor)

Tras `docker compose run --rm app bash`:

```bash
uv --version
uv python list
uv run fastapi --version
```

## Verificación rápida

### En el Mac (host)

```bash
docker --version
docker compose version
```

### Dentro del contenedor

```bash
docker compose run --rm app bash -lc 'uv --version && uv python list && uv run fastapi --version'
```

Equivalente tras entrar con `docker compose run --rm app bash` y ejecutar los mismos comandos a mano.

### Si también instalaste uv en el Mac

Puedes ejecutar en el host (fuera de Docker):

```bash
uv --version
uv python list
uv run fastapi --version
```

(En el host, `uv python list` reflejará los runtimes que uv haya instalado en tu usuario, no necesariamente los del contenedor.)

## Estructura del repo

| Ruta | Descripción |
|------|-------------|
| `app/main.py` | Aplicación FastAPI mínima |
| `app/llm_demo.py`, `app/schemas_llm.py` | Demo OpenAI **Responses API** (`POST /llm/demo`) |
| `notebooks/plantilla_ejercicios.ipynb` | Sesión 1: OpenAI 2a/2b, 3 Anthropic, 4 Gemini (`google-genai`), 5 tokens (`tiktoken` + `count_tokens`) |
| `pyproject.toml` / `uv.lock` | Proyecto uv y dependencias fijadas |
| `Dockerfile` / `docker-compose.yml` | Imagen y servicio de desarrollo |
| `docker/entrypoint.sh` | `uv sync --frozen` antes del comando del servicio |

## Automatizaciones Cursor

El proyecto incluye una capa de trabajo para Cursor en:

- `.cursor/commands/`
- `.cursor/rules/`
- `.cursor/skills/`
- `.cursor/agents/`

### Pipeline recomendado

1. `start-task`
2. `requirement-write` o `write-feature` cuando falte especificación
3. `requirement-validate`
4. `requirement-design`
5. `requirement-tasks`
6. implementación
7. `check-quality` / `check-architecture` / `testing` / `check-dod`
8. `update-docs`
9. `commit-pending`
10. `finish-task`

### Comandos principales

- `start-task`: arranca trabajo desde un documento canónico del Second Brain.
- `requirement-write`: crea o refina una especificación ejecutable.
- `requirement-validate`: revisa si una tarea está lista para implementarse sin bloquear por burocracia.
- `requirement-design`: transforma el requirement en diseño técnico pequeño y verificable.
- `requirement-tasks`: divide el diseño en baby steps con verificación y commits sugeridos.
- `check-quality`: revisión de calidad y mantenibilidad.
- `check-architecture`: revisión ligera de límites y responsabilidades.
- `testing`: validación automática o manual proporcional al cambio.
- `check-dod`: cierre contra definition of done real.
- `commit-pending`: commits pequeños, ligados a una sesión y documentados en el Second Brain.
- `update-docs`: sincroniza repo y `second-brain-master-ia` por sesión o temática.
- `finish-task`: cierre operativo de la tarea.
- `session-review`: retrospectiva de cierre de cada sesión.

### Skills y subagentes

- `master-ia-tutor`: apoyo pedagógico para entender conceptos del máster.
- `requirement-validator-light`: skill reutilizable para validar requirements y riesgos.
- `validation-pass-fastapi`: skill para pases finales de validación en proyectos Python/FastAPI.
- `.cursor/agents/`: subagentes técnicos ligeros para requirements, diseño, calidad, testing y definition of done.

## Licencia

Por definir (uso académico personal).
