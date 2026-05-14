"""Audit identifiers and safe metadata helpers (no raw sensitive dumps)."""

from __future__ import annotations

import hashlib
import logging
from uuid import uuid4

logger = logging.getLogger(__name__)


def new_audit_id(prefix: str = "aud") -> str:
    """Return a short stable identifier for correlating guardrail decisions."""

    return f"{prefix}_{uuid4().hex[:12]}"


def content_fingerprint(text: str, *, length: int = 16) -> str:
    """Return a short hex digest for correlating content without storing raw text."""

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digest[:length]


def log_guardrail_event(
    event: str,
    *,
    audit_id: str,
    guardrail_id: str,
    layer: str,
    passed: bool,
    rollout: str,
    policy: str | None = None,
    reason_code: str | None = None,
    latency_ms: int | None = None,
    fingerprint: str | None = None,
) -> None:
    """Emit structured guardrail metrics without raw user content."""

    logger.info(
        event,
        extra={
            "audit_id": audit_id,
            "guardrail_id": guardrail_id,
            "layer": layer,
            "passed": passed,
            "rollout": rollout,
            "policy": policy,
            "reason_code": reason_code,
            "latency_ms": latency_ms,
            "content_fingerprint": fingerprint,
        },
    )
