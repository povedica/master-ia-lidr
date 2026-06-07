"""Semantic cache orchestration (lookup, threshold, log-only, writes)."""

from __future__ import annotations

import logging
from time import perf_counter

from app.config import Settings
from app.services.semantic_cache.artifacts import structured_bundle_from_artifact_fields
from app.services.semantic_cache.contracts import (
    CacheDecisionStatus,
    CacheLookupResult,
    CacheMissReason,
    CacheWriteDecision,
    CachedEstimationArtifact,
    SemanticCacheLookupRequest,
    SemanticCacheWriteRequest,
)
from app.services.semantic_cache.embeddings import EmbeddingProvider
from app.services.semantic_cache.repository import (
    SemanticCacheRepository,
    json_serialized_size_bytes,
)
from app.services.llm_service import StructuredEstimateBundle

logger = logging.getLogger(__name__)


class SemanticCacheService:
    """Coordinates embeddings, repository lookup, and guarded write decisions."""

    def __init__(
        self,
        *,
        settings: Settings,
        repository: SemanticCacheRepository,
        embedder: EmbeddingProvider,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._embedder = embedder

    def _lookup_allowed(self, lookup: SemanticCacheLookupRequest) -> bool:
        if not self._settings.semantic_cache_allowed_endpoint(lookup.endpoint):
            return False
        if not self._settings.semantic_cache_allowed_operation(lookup.operation):
            return False
        return self._settings.semantic_cache_allowed_tenant(lookup.tenant_id)

    async def evaluate_lookup(
        self, lookup: SemanticCacheLookupRequest
    ) -> tuple[CacheLookupResult, list[float] | None]:
        """Run embedding + neighbor search with rollout-aware decisions.

        Returns the lookup result and the query embedding when computed (for reuse on write).
        """

        if not self._settings.semantic_cache_feature_active():
            return (
                CacheLookupResult(
                    status=CacheDecisionStatus.disabled,
                    miss_reason=CacheMissReason.disabled,
                    bucket=lookup.bucket,
                ),
                None,
            )

        if not self._lookup_allowed(lookup):
            logger.info(
                "semantic_cache.disabled",
                extra={"request_id": lookup.request_id, "reason": "allowlist"},
            )
            return (
                CacheLookupResult(
                    status=CacheDecisionStatus.disabled,
                    miss_reason=CacheMissReason.disabled,
                    bucket=lookup.bucket,
                ),
                None,
            )

        if not self._settings.semantic_cache_store_available():
            return (
                CacheLookupResult(
                    status=CacheDecisionStatus.miss,
                    miss_reason=CacheMissReason.store_error,
                    bucket=lookup.bucket,
                ),
                None,
            )

        logger.info(
            "semantic_cache.lookup_started",
            extra={
                "request_id": lookup.request_id,
                "operation": lookup.operation,
                "bucket": lookup.bucket.display_key,
            },
        )
        embed_started = perf_counter()
        try:
            vector = await self._embedder.embed(lookup.vector_text)
        except Exception as exc:
            logger.warning(
                "semantic_cache.error",
                extra={
                    "request_id": lookup.request_id,
                    "stage": "embedding",
                    "error_type": type(exc).__name__,
                },
            )
            return (
                CacheLookupResult(
                    status=CacheDecisionStatus.error,
                    miss_reason=CacheMissReason.embedding_error,
                    bucket=lookup.bucket,
                ),
                None,
            )
        embed_ms = int((perf_counter() - embed_started) * 1000)

        lookup_started = perf_counter()
        try:
            neighbors = await self._repository.nearest_neighbors(
                bucket_hash=lookup.bucket.bucket_hash,
                query_vector=vector,
                k=self._settings.semantic_cache_max_candidates,
            )
        except Exception as exc:
            logger.warning(
                "semantic_cache.error",
                extra={
                    "request_id": lookup.request_id,
                    "stage": "lookup",
                    "error_type": type(exc).__name__,
                },
            )
            return (
                CacheLookupResult(
                    status=CacheDecisionStatus.error,
                    miss_reason=CacheMissReason.store_error,
                    bucket=lookup.bucket,
                ),
                None,
            )
        lookup_ms = int((perf_counter() - lookup_started) * 1000)

        thr = float(self._settings.semantic_cache_similarity_threshold)
        if not neighbors:
            logger.info(
                "semantic_cache.lookup_completed",
                extra={
                    "request_id": lookup.request_id,
                    "bucket": lookup.bucket.display_key,
                    "latency_ms_embedding": embed_ms,
                    "latency_ms_lookup": lookup_ms,
                    "candidate_count": 0,
                    "decision": "miss",
                    "miss_reason": CacheMissReason.bucket_empty.value,
                },
            )
            return (
                CacheLookupResult(
                    status=CacheDecisionStatus.miss,
                    miss_reason=CacheMissReason.bucket_empty,
                    bucket=lookup.bucket,
                    top_score=None,
                    would_hit=False,
                ),
                vector,
            )

        top = neighbors[0]
        score = float(top.similarity)
        would_hit = score >= thr

        if self._settings.semantic_cache_log_only:
            logger.info(
                "semantic_cache.log_only_candidate",
                extra={
                    "request_id": lookup.request_id,
                    "bucket": lookup.bucket.display_key,
                    "top_score": score,
                    "threshold": thr,
                    "would_hit": would_hit,
                    "latency_ms_embedding": embed_ms,
                    "latency_ms_lookup": lookup_ms,
                },
            )
            logger.info(
                "semantic_cache.lookup_completed",
                extra={
                    "request_id": lookup.request_id,
                    "candidate_count": len(neighbors),
                    "decision": "log_only",
                    "top_score": score,
                    "latency_ms_embedding": embed_ms,
                    "latency_ms_lookup": lookup_ms,
                },
            )
            return (
                CacheLookupResult(
                    status=CacheDecisionStatus.log_only,
                    miss_reason=CacheMissReason.log_only,
                    bucket=lookup.bucket,
                    top_score=score,
                    entry=top,
                    would_hit=would_hit,
                ),
                vector,
            )

        if not self._settings.semantic_cache_enabled:
            logger.info(
                "semantic_cache.lookup_completed",
                extra={
                    "request_id": lookup.request_id,
                    "candidate_count": len(neighbors),
                    "decision": "miss",
                    "miss_reason": CacheMissReason.disabled.value,
                    "top_score": score,
                },
            )
            return (
                CacheLookupResult(
                    status=CacheDecisionStatus.miss,
                    miss_reason=CacheMissReason.disabled,
                    bucket=lookup.bucket,
                    top_score=score,
                    would_hit=would_hit,
                ),
                vector,
            )

        if not would_hit:
            logger.info(
                "semantic_cache.miss",
                extra={
                    "request_id": lookup.request_id,
                    "bucket": lookup.bucket.display_key,
                    "top_score": score,
                    "threshold": thr,
                    "miss_reason": CacheMissReason.low_score.value,
                },
            )
            logger.info(
                "semantic_cache.lookup_completed",
                extra={
                    "request_id": lookup.request_id,
                    "candidate_count": len(neighbors),
                    "decision": "miss",
                    "top_score": score,
                },
            )
            return (
                CacheLookupResult(
                    status=CacheDecisionStatus.miss,
                    miss_reason=CacheMissReason.low_score,
                    bucket=lookup.bucket,
                    top_score=score,
                    would_hit=False,
                ),
                vector,
            )

        try:
            structured_bundle_from_artifact_fields(
                artifact=top.artifact.model_dump(mode="json"),
                prompt_version=top.artifact.prompt_version,
                examples_version=top.artifact.examples_version,
                model=top.artifact.model,
                provider=top.artifact.provider,
            )
        except Exception:
            logger.warning(
                "semantic_cache.validation_failed_on_read",
                extra={"request_id": lookup.request_id, "bucket": lookup.bucket.display_key},
            )
            return (
                CacheLookupResult(
                    status=CacheDecisionStatus.miss,
                    miss_reason=CacheMissReason.payload_invalid,
                    bucket=lookup.bucket,
                    top_score=score,
                    would_hit=False,
                ),
                vector,
            )

        logger.info(
            "semantic_cache.hit",
            extra={
                "request_id": lookup.request_id,
                "bucket": lookup.bucket.display_key,
                "top_score": score,
                "threshold": thr,
            },
        )
        logger.info(
            "semantic_cache.lookup_completed",
            extra={
                "request_id": lookup.request_id,
                "candidate_count": len(neighbors),
                "decision": "hit",
                "top_score": score,
                "latency_ms_embedding": embed_ms,
                "latency_ms_lookup": lookup_ms,
            },
        )
        return (
            CacheLookupResult(
                status=CacheDecisionStatus.hit,
                miss_reason=None,
                bucket=lookup.bucket,
                top_score=score,
                entry=top,
                would_hit=True,
            ),
            vector,
        )

    def bundle_from_hit(self, lookup_result: CacheLookupResult) -> StructuredEstimateBundle | None:
        """Materialize a structured bundle from a validated hit (``lookup_result.entry`` must be set)."""

        if lookup_result.entry is None:
            return None
        top = lookup_result.entry
        try:
            return structured_bundle_from_artifact_fields(
                artifact=top.artifact.model_dump(mode="json"),
                prompt_version=top.artifact.prompt_version,
                examples_version=top.artifact.examples_version,
                model=top.artifact.model,
                provider=top.artifact.provider,
            )
        except Exception:
            return None

    async def maybe_write_validated(
        self,
        *,
        lookup: SemanticCacheLookupRequest,
        embedding: list[float],
        artifact: CachedEstimationArtifact,
        safe_to_cache: bool,
        safe_to_display: bool,
        success: bool,
    ) -> CacheWriteDecision:
        """Persist only when rollout, safety, and payload size allow it."""

        if not self._settings.semantic_cache_feature_active():
            return CacheWriteDecision(wrote=False, skip_reason="feature_inactive")
        if not self._settings.semantic_cache_store_available():
            logger.info("semantic_cache.write_skipped", extra={"reason": "no_store"})
            return CacheWriteDecision(wrote=False, skip_reason="no_store")
        if not self._lookup_allowed(lookup):
            return CacheWriteDecision(wrote=False, skip_reason="allowlist")
        if not success:
            return CacheWriteDecision(wrote=False, skip_reason="not_success")
        if not safe_to_cache or not safe_to_display:
            logger.info("semantic_cache.write_skipped", extra={"reason": "not_safe"})
            return CacheWriteDecision(wrote=False, skip_reason="not_safe")
        if artifact.degraded:
            return CacheWriteDecision(wrote=False, skip_reason="degraded")

        payload = SemanticCacheWriteRequest(lookup=lookup, embedding=embedding, artifact=artifact)
        size = json_serialized_size_bytes(payload.model_dump(mode="json"))
        if size > self._settings.semantic_cache_max_payload_bytes:
            logger.info(
                "semantic_cache.write_skipped",
                extra={"reason": "payload_too_large", "bytes": size},
            )
            return CacheWriteDecision(wrote=False, skip_reason="payload_too_large")

        try:
            await self._repository.write(payload, ttl_seconds=self._settings.semantic_cache_ttl_seconds)
        except Exception as exc:
            logger.warning(
                "semantic_cache.error",
                extra={
                    "request_id": lookup.request_id,
                    "stage": "write",
                    "error_type": type(exc).__name__,
                },
            )
            return CacheWriteDecision(wrote=False, skip_reason="store_error")

        logger.info(
            "semantic_cache.write_completed",
            extra={"request_id": lookup.request_id, "bucket": lookup.bucket.display_key},
        )
        return CacheWriteDecision(wrote=True, skip_reason=None)

    async def embed_for_request(self, vector_text: str) -> list[float]:
        """Compute embedding for cache writes (after a successful LLM path)."""

        return await self._embedder.embed(vector_text)
