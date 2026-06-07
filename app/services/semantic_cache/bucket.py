"""Deterministic cache bucket and embedding text surface for estimation v2."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.config import Settings
from app.schemas.estimation_request import EstimationRequest
from app.services.semantic_cache.contracts import SemanticCacheBucket


def _json_canonical(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def build_vector_text_surface(*, request: EstimationRequest, assessment_surface: str) -> str:
    """Concatenate normalized free-text surfaces (no structured bucket fields)."""

    parts: list[str] = [
        request.project_summary.strip(),
        request.project_description.strip(),
    ]
    if request.project_name:
        parts.append(request.project_name.strip())
    surf = assessment_surface.strip()
    if surf:
        parts.append(surf)
    return "\n\n".join(p for p in parts if p)


def build_semantic_cache_bucket(
    *,
    request: EstimationRequest,
    settings: Settings,
    prompt_version: str,
    examples_version: str,
    output_schema_version: str,
    guardrail_rules_version: str,
    operation: str,
    tenant_id: str,
) -> SemanticCacheBucket:
    """Hash prompt-affecting structured fields into a deterministic bucket."""

    namespace = settings.semantic_cache_namespace.strip() or "semantic:estimation"
    payload: dict[str, Any] = {
        "cache_schema_version": settings.semantic_cache_cache_schema_version.strip() or "1",
        "embedding_model_version": settings.semantic_cache_embedding_model_version.strip(),
        "examples_version": examples_version,
        "guardrail_rules_version": guardrail_rules_version.strip(),
        "operation": operation,
        "output_format": request.output_format.value,
        "output_schema_version": output_schema_version.strip() or "1",
        "preprocessing": request.preprocessing.strip(),
        "project_type": request.project_type.value,
        "prompt_version": prompt_version.strip(),
        "tenant_id": tenant_id.strip() or "default",
        "detail_level": request.detail_level.value,
        "industry": request.industry.value if request.industry else None,
    }
    digest = hashlib.sha256(_json_canonical(payload)).hexdigest()
    display_key = f"{namespace}:{digest[:16]}"
    return SemanticCacheBucket(bucket_hash=digest, namespace=namespace, display_key=display_key)


def input_fingerprint_for_vector_text(vector_text: str) -> str:
    normalized = "\n".join(line.strip() for line in vector_text.splitlines() if line.strip())
    body = normalized.encode("utf-8")
    return hashlib.sha256(body).hexdigest()
