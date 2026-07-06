"""Runtime config API: GET/PUT model and retrieval overrides (feature-057).

Config endpoints are intentionally open in dev (no API key) per the work
item's fork choice; retrieval/RAG routes keep their feature-056 auth.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.schemas.runtime_config import (
    RuntimeModelConfig,
    RuntimeModelConfigUpdate,
    RuntimeRetrievalConfig,
    RuntimeRetrievalConfigUpdate,
)
from app.services.runtime_config import (
    RuntimeConfigRedisClient,
    RuntimeConfigUnavailableError,
    build_redis_client,
    get_effective_models_config,
    get_effective_retrieval_config,
    update_models_config,
    update_retrieval_config,
)

router = APIRouter(prefix="/config", tags=["runtime-config"])

_UNAVAILABLE_DETAIL = "Runtime config store is unavailable; try again later."


def get_runtime_redis_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> RuntimeConfigRedisClient | None:
    return build_redis_client(settings)


@router.get("/retrieval", response_model=RuntimeRetrievalConfig)
async def get_retrieval_config(
    settings: Annotated[Settings, Depends(get_settings)],
    redis_client: Annotated[RuntimeConfigRedisClient | None, Depends(get_runtime_redis_client)],
) -> RuntimeRetrievalConfig:
    """Return effective retrieval config (Redis override merged over ``Settings``)."""

    return await get_effective_retrieval_config(settings, redis_client)


@router.put("/retrieval", response_model=RuntimeRetrievalConfig)
async def put_retrieval_config(
    payload: RuntimeRetrievalConfigUpdate,
    settings: Annotated[Settings, Depends(get_settings)],
    redis_client: Annotated[RuntimeConfigRedisClient | None, Depends(get_runtime_redis_client)],
) -> RuntimeRetrievalConfig:
    """Persist a partial retrieval override to Redis and return the merged config."""

    try:
        return await update_retrieval_config(settings, redis_client, payload)
    except RuntimeConfigUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_UNAVAILABLE_DETAIL,
        ) from exc


@router.get("/models", response_model=RuntimeModelConfig)
async def get_models_config(
    settings: Annotated[Settings, Depends(get_settings)],
    redis_client: Annotated[RuntimeConfigRedisClient | None, Depends(get_runtime_redis_client)],
) -> RuntimeModelConfig:
    """Return effective model config (Redis override merged over ``Settings``)."""

    return await get_effective_models_config(settings, redis_client)


@router.put("/models", response_model=RuntimeModelConfig)
async def put_models_config(
    payload: RuntimeModelConfigUpdate,
    settings: Annotated[Settings, Depends(get_settings)],
    redis_client: Annotated[RuntimeConfigRedisClient | None, Depends(get_runtime_redis_client)],
) -> RuntimeModelConfig:
    """Persist a partial model override to Redis and return the merged config."""

    try:
        return await update_models_config(settings, redis_client, payload)
    except RuntimeConfigUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_UNAVAILABLE_DETAIL,
        ) from exc
