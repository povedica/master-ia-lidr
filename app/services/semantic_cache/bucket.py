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
        "\n".join(d.strip() for d in request.deliverables),
    ]
    if request.project_name:
        parts.append(request.project_name.strip())
    if request.out_of_scope:
        parts.append("\n".join(s.strip() for s in request.out_of_scope if s.strip()))
    if request.external_dependencies:
        parts.append("\n".join(s.strip() for s in request.external_dependencies if s.strip()))
    if request.hosting_notes:
        parts.append(request.hosting_notes.strip())
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
    estimation_mode: str,
) -> SemanticCacheBucket:
    """Hash prompt-affecting structured fields into a deterministic bucket."""

    namespace = settings.semantic_cache_namespace.strip() or "semantic:estimation"
    integration_sorted = sorted({c.value for c in request.integration_categories})
    hosting_sorted: list[str] = []
    if request.hosting_constraints:
        hosting_sorted = sorted({h.value for h in request.hosting_constraints})
    ui_langs = sorted({u.value for u in request.ui_languages})
    payload: dict[str, Any] = {
        "cache_schema_version": settings.semantic_cache_cache_schema_version.strip() or "1",
        "embedding_model_version": settings.semantic_cache_embedding_model_version.strip(),
        "estimation_mode": estimation_mode,
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
        "delivery_approach": request.delivery_approach.value if request.delivery_approach else None,
        "delivery_urgency": request.delivery_urgency.value,
        "industry": request.industry.value if request.industry else None,
        "data_sensitivity": request.data_sensitivity.value,
        "hosting_constraints": hosting_sorted,
        "integration_categories": integration_sorted,
        "ui_languages": ui_langs,
    }
    digest = hashlib.sha256(_json_canonical(payload)).hexdigest()
    display_key = f"{namespace}:{digest[:16]}"
    return SemanticCacheBucket(bucket_hash=digest, namespace=namespace, display_key=display_key)


def input_fingerprint_for_vector_text(vector_text: str) -> str:
    normalized = "\n".join(line.strip() for line in vector_text.splitlines() if line.strip())
    body = normalized.encode("utf-8")
    return hashlib.sha256(body).hexdigest()
