---
name: Master IA Docker uv
overview: Inicializar el repositorio Git, añadir README, crear un enlace simbólico a tu carpeta de Second Brain, y montar un entorno de desarrollo reproducible con Docker + uv (Python 3.11 + FastAPI) con comandos de verificación documentados.
todos:
  - id: git-init
    content: Inicializar git, añadir .gitignore Python/uv/Docker
    status: completed
  - id: uv-project
    content: Crear pyproject.toml (Python 3.11), fastapi[standard], generar uv.lock
    status: completed
  - id: docker
    content: Dockerfile + docker-compose con uv y sync del proyecto
    status: completed
  - id: readme
    content: "README.md: propósito, enlace, Docker, uv, comandos verificación host vs contenedor"
    status: completed
  - id: symlink
    content: Crear learnings/second-brain-master-ia -> ruta Second Brain (comprobar destino)
    status: completed
  - id: verify
    content: Build compose y validar docker/uv/python/fastapi según README
    status: completed
isProject: false
---

# Plan: proyecto Master IA (Git, README, enlace, Docker, uv, FastAPI)

## Contexto del workspace

En [master-ia](.) solo existe [master-ia.code-workspace](master-ia.code-workspace). El resto se creará desde cero.

**Nota sobre la versión de Python:** pediste "Python 3.1"; tu checklist final pide **3.11**. El plan usa **Python 3.11** en todo (coincide con `uv python list` que quieres ver).

---

## 1. Git

- Ejecutar `git init` en la raíz del proyecto.
- Añadir un [.gitignore](.gitignore) mínimo para Python/uv/Docker/OS: `__pycache__/`, `.venv/`, `.env`, `*.pyc`, `.DS_Store`, cachés de herramientas, etc.
- (Opcional) Commit inicial con README + estructura base; solo si lo deseas al implementar.

---

## 2. README.md

- Crear [README.md](README.md) en español con:
  - Título y propósito del repo (Master IA).
  - Sección **Second Brain / enlace** (ruta del symlink y advertencia de que el destino debe existir).
  - Sección **Requisitos en el Mac**: Docker Desktop o motor Docker + plugin Compose (los comandos `docker --version` y `docker compose version` son **en el host**).
  - Sección **Desarrollo con Docker**: cómo construir y entrar al contenedor / levantar el servicio.
  - Sección **uv y Python**: comandos equivalentes **dentro del contenedor** (ver punto 5).
  - Sección **Verificación** con el bloque de comandos que pediste, aclarando qué va en host y qué dentro del contenedor (para no confundir si uv no está instalado en el Mac).

---

## 3. Directorio enlace simbólico

- Destino absoluto (con espacios; hay que citarlo bien en terminal):

`/Users/pablo.poveda/CodeProjects/ticktick/docs/second-brain/03 Projects/Trabajo/Master IA`

- Bajo `learnings/`, crear un symlink con un nombre estable y claro, por ejemplo **`second-brain-master-ia`** (si prefieres otro nombre, se puede cambiar en un solo comando).

- Comando tipo (a ejecutar al implementar, comprobando antes que el destino exista):

`ln -s "/Users/pablo.poveda/CodeProjects/ticktick/docs/second-brain/03 Projects/Trabajo/Master IA" learnings/second-brain-master-ia`

- En README: documentar que es solo un acceso rápido a Obsidian/Second Brain y que no versiona el contenido del otro repo (el symlink puede romperse en otra máquina).

---

## 4. ¿uv en Docker o global en el CLI?

**Recomendación alineada con "trabajaré todo en entorno docker":** instalar **uv dentro de la imagen Docker** como fuente de verdad (versiones fijas, mismo entorno en cualquier máquina).

| Enfoque | Ventaja |
|--------|---------|
| **uv en Docker** (recomendado) | Reproducible; `uv.lock` + imagen; no contamina el Mac. |
| **uv global en el Mac** | Cómodo para scripts fuera del contenedor; duplica responsabilidad de versiones. |

**Host:** solo hace falta **Docker + Compose** (y Git). **uv en el host** es opcional; si lo instalas con el instalador oficial, acelera tareas locales, pero no es obligatorio para cumplir el objetivo "todo en Docker".

---

## 5. Docker + Python 3.11 + FastAPI con uv

Estructura propuesta (nombres ajustables al implementar):

- [Dockerfile](Dockerfile): imagen base ligera (p. ej. `python:3.11-slim` o `ghcr.io/astral-sh/uv:python3.11-bookworm-slim` si quieres la imagen oficial de uv), copiar el proyecto, `uv sync --frozen` en build o en arranque según prefieras lock estricto.
- [docker-compose.yml](docker-compose.yml): servicio `app` (o `dev`) con volumen montado del código para editar desde el host; `working_dir` en la carpeta del proyecto uv; comando por defecto shell o `uvicorn` según prefieras.
- Carpeta del app uv, p. ej. [app/](app/) o raíz con `pyproject.toml` en la raíz del repo.

**Proyecto uv:**

- `pyproject.toml` con `requires-python = ">=3.11,<3.12"` (o similar) y dependencias:
  - `fastapi`
  - extras o paquetes que expongan el CLI: para que exista el comando `fastapi` y funcione `uv run fastapi --version`, conviene **`fastapi[standard]`** (incluye herramientas estándar y el CLI donde aplique según la versión actual de FastAPI).
- `uv lock` generará [uv.lock](uv.lock).

**Python 3.11 en la imagen:**

- En el Dockerfile: fijar imagen 3.11 o ejecutar `uv python install 3.11` si usas una imagen basada en uv sin runtime preinstalado; objetivo: que `uv python list` dentro del contenedor muestre **3.11** instalado/usado por el proyecto.

---

## 6. Checklist final de comandos (como en tu mensaje)

Documentar en README algo equivalente a:

**En el Mac (host):**

```bash
docker --version
docker compose version
```

**Dentro del contenedor** (p. ej. `docker compose run --rm app bash` y luego, o un one-liner):

```bash
uv --version
uv python list
uv run fastapi --version
```

Si en el host también instalas uv globalmente, los mismos tres comandos pueden ejecutarse en el Mac; el README dejará claro cuál es el flujo recomendado (Docker).

---

## 7. Orden de implementación sugerido

1. `git init` + `.gitignore`
2. Crear estructura uv (`pyproject.toml`, dependencias, `uv lock` desde entorno con uv o desde Docker una vez exista el Dockerfile)
3. `Dockerfile` + `docker-compose.yml`
4. `README.md` con enlaces a rutas y comandos
5. Symlink (tras verificar que existe el destino)
6. Probar build + los comandos de verificación

---

## Riesgos / comprobaciones

- La ruta del Second Brain **debe existir** antes del `ln -s`; si no, el enlace fallará o quedará colgante.
- Rutas con espacios: siempre entre comillas en shell.
- El CLI `fastapi` depende de la versión de FastAPI/extras; si `--version` no estuviera disponible en una versión concreta, se ajustará el extra o el comando documentado (p. ej. `python -c "import fastapi; print(fastapi.__version__)"` como respaldo en README).
