#!/usr/bin/env python3
"""Fire many concurrent HTTP requests against a URL (local stress / soak helper).

Uses ``httpx`` async client (already a dev dependency of estimador-cag).

Examples (from the repository root)::

    uv run python dev-tools/stress_api.py --help
    uv run python dev-tools/stress_api.py --url http://127.0.0.1:8000/health --requests 200 --concurrency 20
    uv run python dev-tools/stress_api.py --url http://127.0.0.1:8000/api/v1/estimate \\
        --method POST --random-estimation-request --requests 30 --concurrency 5

Warning: POST ``/api/v1/estimate`` triggers real provider work unless you use mocks/static
fallback; prefer ``/health`` for pure load on the stack. The guardrail returns ``422`` with
``out_of_domain`` when the structured request does not look like a software/project estimate.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

def _estimation_request_body_from_seed(text: str) -> dict[str, Any]:
    """Build a valid ``EstimationRequest`` JSON dict from a free-form seed string."""

    cleaned = text.strip()
    summary = cleaned.replace("\n", " ").strip()
    if len(summary) > 200:
        summary = summary[:197] + "..."
    if len(summary) < 20:
        summary = (summary + " software estimation request.").strip()[:200]
        if len(summary) < 20:
            summary = summary.ljust(20, ".")

    description = cleaned if len(cleaned) >= 100 else (cleaned + "\n" + "y" * 120)[:12000]
    return {
        "project_summary": summary,
        "project_type": "web_saas",
        "target_audience": "b2b_smb",
    "project_description": description,
    "detail_level": "medium",
        "output_format": "phases_table",
        "preprocessing": "none",
        "evaluate": True,
    }


ESTIMATION_REQUESTS: list[str] = [
    # ≤ 50 words
    "Necesito una web para reservas de pistas de pádel. Usuarios registrados, calendario y pagos online. Versión web responsive. Sin app móvil.",
    "Quiero una API que gestione inventario de productos con stock, altas/bajas y consultas. Debe integrarse con un ERP externo.",
    "Landing para un evento con formulario de inscripción y envío de emails. Diseño simple y responsive.",
    "App web para compartir enlaces favoritos entre usuarios con login y etiquetas. Sin app móvil.",
    "Sistema de tickets interno básico con login y creación/seguimiento de incidencias.",
    "Plugin WordPress para mostrar eventos desde una API externa con caché simple.",
    "Chat web básico en tiempo real entre usuarios registrados. Sin historial persistente.",
    "Formulario multi-step para solicitudes con validación y almacenamiento en base de datos.",
    "Script que importe datos CSV a base de datos y exponga un endpoint de consulta.",
    "Panel sencillo para subir imágenes y listarlas con paginación.",

    # ≤ 100 words
    "Aplicación móvil para iOS y Android de gestión de hábitos. Registro de usuario, creación de hábitos, recordatorios diarios y estadísticas básicas. Backend con autenticación, almacenamiento y notificaciones push. Sin funcionalidades sociales. Interfaz sencilla, sin diseño avanzado.",
    "Dashboard web para equipo comercial. Login, visualización de métricas (ventas, leads, conversión), filtros por fechas y exportación a Excel. Integración con CRM existente vía API REST. Acceso por roles (manager/comercial). No requiere app móvil.",
    "Ecommerce básico con catálogo de productos, carrito y pagos. Gestión simple desde panel admin. Sin multidioma ni multi-moneda.",
    "Sistema de reservas para restaurante con selección de mesa, fecha y hora. Confirmación por email y panel de gestión.",
    "App de notas compartidas con usuarios, edición en tiempo real y versionado simple. Backend con API REST.",
    "Plataforma de cursos online con login, listado de cursos, vídeos y progreso de usuario. Sin certificados.",
    "Sistema de encuestas con creación, respuestas anónimas y exportación de resultados.",
    "App móvil de seguimiento de gastos con categorías, gráficos y sincronización en la nube.",
    "Herramienta interna para gestión de tareas con estados, asignaciones y comentarios.",
    "Portal de soporte con base de conocimiento y formulario de contacto integrado.",

    # ≤ 200 words
    "Plataforma web tipo marketplace de servicios locales (fontaneros, electricistas). Usuarios pueden registrarse como cliente o proveedor. Los clientes publican solicitudes y reciben propuestas; los proveedores responden con presupuestos. Incluye sistema de mensajería interna, valoraciones y perfiles públicos. Panel de administración para moderación de usuarios y contenidos. Pagos integrados (Stripe) con comisión por transacción. Backend con API REST, autenticación JWT, base de datos relacional. Frontend en React. Debe ser responsive. No se requiere app móvil en esta fase.",
    "Sistema interno de gestión documental para una empresa legal. Acceso autenticado con roles (admin, abogado, cliente). Subida y almacenamiento de documentos (PDF, Word), organización por casos, búsqueda por texto y metadatos. Control de versiones y registro de actividad. Integración con servicio externo de firma digital. Notificaciones por email cuando hay cambios en documentos. Backend con arquitectura modular, almacenamiento seguro (S3 o similar), cifrado en tránsito. Frontend web con interfaz clara orientada a productividad. Incluye logs, auditoría y permisos granulares por documento.",
    "Aplicación SaaS para gestión de proyectos. Usuarios con roles, creación de proyectos, tareas, dependencias y vistas tipo Kanban. Notificaciones, comentarios y adjuntos. Backend con API REST, base de datos relacional y colas para tareas async. Integración con Slack para alertas. Frontend SPA en React. Incluye autenticación, permisos y panel de administración.",
    "Sistema de analítica web que recoja eventos desde clientes mediante SDK JavaScript. Almacena eventos en backend, procesa métricas básicas (visitas, conversiones) y muestra dashboards. Necesita almacenamiento escalable, procesamiento batch y visualización web. Incluye autenticación y roles.",
    "Plataforma de streaming de vídeo interno. Usuarios autenticados pueden subir vídeos, reproducirlos y organizarlos en categorías. Transcodificación automática, control de acceso por roles y estadísticas de visualización. Backend con almacenamiento en cloud y CDN. Frontend web responsive.",
    "Aplicación móvil de delivery. Usuarios registran dirección, navegan restaurantes, hacen pedidos y pagan online. Backend gestiona pedidos, estados y notificaciones. Panel para restaurantes y administración. Integración con pasarela de pago y geolocalización.",
    "Sistema de gestión de inventario multi-almacén. Productos, stock por ubicación, movimientos, alertas y reportes. Integración con ERP externo. Backend con API, base de datos relacional y autenticación. Frontend web con dashboards y filtros avanzados.",
    "Portal educativo con usuarios (alumnos/profesores), cursos, lecciones, evaluaciones y progreso. Incluye sistema de exámenes, calificaciones y panel administrativo. Backend modular, almacenamiento de contenido y notificaciones. Frontend web responsive.",
    "Aplicación de citas médicas. Pacientes y doctores con perfiles, agenda, reservas, recordatorios y historial. Integración con calendario externo y notificaciones. Backend con API segura y cumplimiento básico de privacidad.",
    "Sistema de reporting financiero. Importa datos desde múltiples fuentes, normaliza y genera informes personalizables. Dashboard con gráficos, exportación y roles. Backend con procesamiento batch y almacenamiento optimizado.",
]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Parallel HTTP requests with httpx.")
    p.add_argument(
        "--url",
        default="http://127.0.0.1:8000/health",
        help="Target URL (default: local health).",
    )
    p.add_argument(
        "--method",
        default="GET",
        choices=("GET", "POST", "PUT", "PATCH", "DELETE"),
        help="HTTP method.",
    )
    p.add_argument(
        "--requests",
        type=int,
        default=100,
        metavar="N",
        help="Total number of requests to send.",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=10,
        metavar="N",
        help="Maximum in-flight requests at once.",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Per-request timeout in seconds.",
    )
    p.add_argument(
        "--json-body",
        default=None,
        help="JSON string for request body (sets Content-Type: application/json).",
    )
    p.add_argument(
        "--json-file",
        type=Path,
        default=None,
        help="Path to JSON file for body (overrides --json-body if both set).",
    )
    p.add_argument(
        "--header",
        action="append",
        default=[],
        metavar="H",
        help='Extra header "Name: Value" (repeatable).',
    )
    p.add_argument(
        "--random-estimation-request",
        action="store_true",
        help=(
            "Each request sends a random structured EstimationRequest JSON body built from "
            "ESTIMATION_REQUESTS (for POST /api/v1/estimate stress). Mutually exclusive "
            "with --json-body and --json-file; requires --method POST."
        ),
    )
    return p.parse_args()


def _load_json_body(args: argparse.Namespace) -> bytes | None:
    if args.json_file is not None:
        data = args.json_file.read_text(encoding="utf-8")
        obj: Any = json.loads(data)
        return json.dumps(obj).encode("utf-8")
    if args.json_body is not None:
        obj = json.loads(args.json_body)
        return json.dumps(obj).encode("utf-8")
    return None


def _extra_headers(raw: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in raw:
        if ":" not in line:
            raise ValueError(f'Invalid header (expected "Name: Value"): {line!r}')
        name, value = line.split(":", 1)
        out[name.strip()] = value.strip()
    return out


def _percentiles_ms(latencies_ms: list[float]) -> tuple[float | None, float | None]:
    if not latencies_ms:
        return None, None
    xs = sorted(latencies_ms)
    if len(xs) == 1:
        return xs[0], xs[0]
    p50 = statistics.median(xs)
    k = max(0, min(len(xs) - 1, round(0.95 * (len(xs) - 1))))
    p95 = xs[k]
    return p50, p95


async def _run(args: argparse.Namespace) -> int:
    if args.requests < 1:
        print("error: --requests must be >= 1", file=sys.stderr)
        return 2
    if args.concurrency < 1:
        print("error: --concurrency must be >= 1", file=sys.stderr)
        return 2

    body = _load_json_body(args)
    use_random_transcription = args.random_estimation_request
    headers = _extra_headers(args.header)
    if body is not None or use_random_transcription:
        headers.setdefault("Content-Type", "application/json")

    sem = asyncio.Semaphore(args.concurrency)
    status_counts: Counter[int] = Counter()
    errors: list[str] = []
    latencies_ms: list[float] = []

    timeout = httpx.Timeout(args.timeout)

    async def one(client: httpx.AsyncClient) -> None:
        async with sem:
            if use_random_transcription:
                payload = json.dumps(
                    _estimation_request_body_from_seed(random.choice(ESTIMATION_REQUESTS)),
                    ensure_ascii=False,
                ).encode("utf-8")
            else:
                payload = body
            t0 = time.perf_counter()
            try:
                r = await client.request(
                    args.method,
                    args.url,
                    content=payload,
                    headers=headers or None,
                )
                dt_ms = (time.perf_counter() - t0) * 1000
                latencies_ms.append(dt_ms)
                status_counts[r.status_code] += 1
            except httpx.RequestError as e:
                dt_ms = (time.perf_counter() - t0) * 1000
                latencies_ms.append(dt_ms)
                errors.append(f"{type(e).__name__}: {e}")

    wall0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=timeout) as client:
        await asyncio.gather(*(one(client) for _ in range(args.requests)))
    wall_s = time.perf_counter() - wall0

    ok = sum(status_counts[s] for s in status_counts if 200 <= s < 300)
    p50, p95 = _percentiles_ms(latencies_ms)

    print(f"url={args.url} method={args.method} total={args.requests} concurrency={args.concurrency}")
    print(f"wall_time_s={wall_s:.3f} rps={args.requests / wall_s:.2f}")
    print(f"status_codes={dict(status_counts)}")
    print(f"2xx_count={ok} error_count={len(errors)}")
    if latencies_ms:
        print(
            f"latency_ms min={min(latencies_ms):.1f} p50={p50:.1f} p95={p95:.1f} max={max(latencies_ms):.1f}"
        )
    if errors:
        err_hist = Counter(errors)
        print("errors (top 8):")
        for msg, n in err_hist.most_common(8):
            print(f"  {n}x {msg}")
        return 1 if ok == 0 else 0

    return 0 if ok == args.requests else 1


def main() -> None:
    args = _parse_args()
    if args.random_estimation_request:
        if args.json_body is not None or args.json_file is not None:
            print(
                "error: --random-estimation-request cannot be combined with "
                "--json-body or --json-file",
                file=sys.stderr,
            )
            sys.exit(2)
        if args.method != "POST":
            print(
                "error: --random-estimation-request requires --method POST",
                file=sys.stderr,
            )
            sys.exit(2)
    try:
        if args.json_body is not None or args.json_file is not None:
            _load_json_body(args)  # validate early
        _extra_headers(args.header)
    except (json.JSONDecodeError, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
