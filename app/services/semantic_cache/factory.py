"""Build ``SemanticCacheService`` from application settings."""

from __future__ import annotations

import logging

from app.config import Settings
from app.services.semantic_cache.embeddings import EmbeddingProvider, FakeEmbeddingProvider
from app.services.semantic_cache.openai_embeddings import OpenAIEmbeddingProvider
from app.services.semantic_cache.repository import (
    InMemorySemanticCacheRepository,
    NullSemanticCacheRepository,
    SemanticCacheRepository,
)
from app.services.semantic_cache.service import SemanticCacheService

logger = logging.getLogger(__name__)


def build_semantic_cache_service(settings: Settings) -> SemanticCacheService | None:
    """Return a configured service, or ``None`` when semantic cache is fully disabled."""

    if settings.semantic_cache_fully_off():
        return None

    repo: SemanticCacheRepository
    if not settings.semantic_cache_store_available():
        if settings.semantic_cache_enabled:
            logger.warning(
                "semantic_cache.store_not_configured",
                extra={"detail": "Semantic cache serving is enabled but no store is configured; lookups will miss."},
            )
        repo = NullSemanticCacheRepository()
    elif settings.semantic_cache_use_memory_store:
        repo = InMemorySemanticCacheRepository()
    else:
        logger.warning(
            "semantic_cache.redis_adapter_not_implemented",
            extra={
                "detail": "SEMANTIC_CACHE_REDIS_URL is set but Redis vector adapter is not wired yet; using null store.",
            },
        )
        repo = NullSemanticCacheRepository()

    embedder: EmbeddingProvider
    provider = settings.semantic_cache_embedding_provider.strip().lower()
    if provider == "openai" and settings.openai_api_key.strip():
        embedder = OpenAIEmbeddingProvider(settings)
    else:
        if settings.semantic_cache_feature_active() and provider == "openai":
            logger.warning(
                "semantic_cache.embedding_fallback_fake",
                extra={"detail": "OpenAI embedding requested but OPENAI_API_KEY is empty; using deterministic fake embeddings."},
            )
        embedder = FakeEmbeddingProvider()

    return SemanticCacheService(settings=settings, repository=repo, embedder=embedder)
