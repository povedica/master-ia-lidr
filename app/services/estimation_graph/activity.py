"""Live per-agent activity log for the supervisor/worker graph (didactic UI feed).

Streaming endpoints drive the graph with ``astream(..., stream_mode="updates")``
and append a short, human-readable line per node here.

Two backends behind one contract (``reset`` / ``append`` / ``read``):

* **Redis** when ``REDIS_URL`` is configured — list ``graph:activity:{id}`` with TTL.
* **In-process dict** otherwise — tests / single-process dev without Redis.

``describe_node`` is pure and exception-free: unknown shapes degrade to a generic line.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_KEY_PREFIX = "graph:activity:"

_NODE_KEYS: dict[str, str] = {
    "supervisor": "supervisor",
    "requirements_extractor": "requirements",
    "budget_searcher": "budget_search",
    "estimate_generator": "estimate",
    "coherence_validator": "validator",
    "human_review": "human_review",
}

_NODE_LABELS: dict[str, str] = {
    "supervisor": "Supervisor",
    "requirements": "Requirements",
    "budget_search": "Budget search",
    "estimate": "Estimate",
    "validator": "Validator",
    "human_review": "Human review",
}


def _as_updates(update) -> list[dict]:
    """Normalise a node update to a list of dicts."""
    if isinstance(update, list):
        return [u for u in update if isinstance(u, dict)]
    if isinstance(update, dict):
        return [update]
    return []


def describe_node(node_name: str, update) -> list[dict]:
    """Map one ``astream`` chunk entry to didactic activity lines."""
    try:
        if node_name == "__interrupt__":
            return [
                {
                    "node": "gate",
                    "label": "Pausa",
                    "message": "⏸ esperando revisión humana",
                }
            ]

        key = _NODE_KEYS.get(node_name, node_name)
        label = _NODE_LABELS.get(key, key)
        updates = _as_updates(update)

        if node_name == "supervisor":
            reason = _first(updates, "route_reason") or "?"
            target = _first(updates, "last_route") or "?"
            return [
                {
                    "node": key,
                    "label": label,
                    "message": f"Ruta → {target} ({reason})",
                }
            ]

        if node_name == "requirements_extractor":
            requirements = _first(updates, "requirements") or []
            return [
                {
                    "node": key,
                    "label": label,
                    "message": f"{len(requirements)} requisitos extraídos",
                }
            ]

        if node_name == "budget_searcher":
            matches = _first(updates, "budget_matches") or []
            no_match = sum(1 for row in matches if row.get("no_match"))
            return [
                {
                    "node": key,
                    "label": label,
                    "message": f"{len(matches)} filas · {no_match} sin precedente",
                }
            ]

        if node_name == "estimate_generator":
            estimate = _first(updates, "estimate") or {}
            total = estimate.get("total_hours")
            return [
                {
                    "node": key,
                    "label": label,
                    "message": f"Total {total}h" if total is not None else "estimación generada",
                }
            ]

        if node_name == "coherence_validator":
            confidence = _first(updates, "confidence")
            validation = _first(updates, "validation") or {}
            reasons = validation.get("review_reasons") or []
            tail = f" · {len(reasons)} señales HITL" if reasons else ""
            return [
                {
                    "node": key,
                    "label": label,
                    "message": f"Confianza {confidence}{tail}",
                }
            ]

        if node_name == "human_review":
            resolution = _first(updates, "human_resolution") or {}
            action = resolution.get("action") or "resumed"
            return [
                {
                    "node": key,
                    "label": label,
                    "message": f"Resolución humana: {action}",
                }
            ]

        return [{"node": key, "label": label, "message": "hecho"}]
    except Exception as exc:  # noqa: BLE001 — never break the streaming loop
        logger.warning(
            "describe_node_failed",
            extra={"node": node_name, "error": str(exc)[:200]},
        )
        return [{"node": node_name, "label": node_name, "message": "…"}]


def _first(updates: list[dict], field: str):
    for u in updates:
        if field in u:
            return u[field]
    return None


class GraphActivityLog:
    """Redis-list-or-dict store of per-run didactic activity lines."""

    def __init__(self, redis_client=None, ttl: int = 3600) -> None:
        self._redis = redis_client
        self._ttl = ttl
        self._mem: dict[str, list[dict]] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_settings(cls, settings) -> GraphActivityLog:
        """Build the store, preferring Redis and degrading to the dict fallback."""
        redis_client = None
        redis_url = (getattr(settings, "redis_url", None) or "").strip()
        if redis_url:
            try:
                import redis

                redis_client = redis.from_url(redis_url, decode_responses=True)
                redis_client.ping()
            except Exception as exc:  # noqa: BLE001 — fall back to in-memory
                logger.warning(
                    "graph_activity_redis_unavailable",
                    extra={
                        "reason": "setup_failed",
                        "error_type": type(exc).__name__,
                    },
                )
                redis_client = None
        return cls(redis_client=redis_client)

    def reset(self, estimation_id: str) -> None:
        """Clear the log for a fresh START (resume appends, so it is not reset)."""
        if self._redis is not None:
            self._redis.delete(_KEY_PREFIX + estimation_id)
            return
        with self._lock:
            self._mem.pop(estimation_id, None)

    def append(self, estimation_id: str, node: str, label: str, message: str) -> None:
        """Append one activity line (seq = current length)."""
        entry = {
            "node": node,
            "label": label,
            "message": message,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        if self._redis is not None:
            key = _KEY_PREFIX + estimation_id
            pipe = self._redis.pipeline()
            entry["seq"] = self._redis.llen(key)
            pipe.rpush(key, json.dumps(entry))
            pipe.expire(key, self._ttl)
            pipe.execute()
            return
        with self._lock:
            bucket = self._mem.setdefault(estimation_id, [])
            entry["seq"] = len(bucket)
            bucket.append(entry)

    def read(self, estimation_id: str) -> list[dict]:
        """Return every activity line for a run, in order."""
        if self._redis is not None:
            raw = self._redis.lrange(_KEY_PREFIX + estimation_id, 0, -1)
            return [json.loads(item) for item in raw]
        with self._lock:
            return list(self._mem.get(estimation_id, []))
