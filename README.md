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
| `pyproject.toml` / `uv.lock` | Proyecto uv y dependencias fijadas |
| `Dockerfile` / `docker-compose.yml` | Imagen y servicio de desarrollo |
| `docker/entrypoint.sh` | `uv sync --frozen` antes del comando del servicio |

## Licencia

Por definir (uso académico personal).
