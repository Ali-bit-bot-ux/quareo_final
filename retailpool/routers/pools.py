"""
Pool Router — REST API for co-buying pool management.

Endpoints:
  POST /pools/create       — open a new pool
  POST /pools/{id}/join    — join an existing pool
  GET  /pools/{id}/status  — get pool status + quorum progress
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from retailpool.database import get_db
from retailpool.schemas.pool import PoolCreate, PoolJoin, PoolOut, PoolStatusOut
from retailpool.services.pool_service import PoolService

router = APIRouter(prefix="/pools", tags=["Co-Buying Pools"])


def _get_pool_service(db: AsyncSession = Depends(get_db)) -> PoolService:
    """FastAPI Dependency Injection for PoolService."""
    return PoolService(db=db)


@router.post(
    "/create",
    response_model=PoolOut,
    status_code=status.HTTP_201_CREATED,
    summary="Open a new co-buying pool",
)
async def create_pool(
    data: PoolCreate,
    svc: PoolService = Depends(_get_pool_service),
) -> PoolOut:
    """
    Create a co-buying pool for a product found by the niche scanner.
    The pool stays OPEN until quorum is reached or expiration.
    """
    try:
        return await svc.create_pool(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/{pool_id}/join",
    response_model=PoolStatusOut,
    summary="Join an existing pool",
)
async def join_pool(
    pool_id: uuid.UUID,
    data: PoolJoin,
    svc: PoolService = Depends(_get_pool_service),
) -> PoolStatusOut:
    """
    Add a participant to the pool. Automatically closes the pool
    when both quantity and amount targets are met.
    """
    try:
        return await svc.join_pool(pool_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/{pool_id}/status",
    response_model=PoolStatusOut,
    summary="Get pool status and quorum progress",
)
async def get_pool_status(
    pool_id: uuid.UUID,
    svc: PoolService = Depends(_get_pool_service),
) -> PoolStatusOut:
    """
    Returns pool info, participant list, and quorum completion
    percentage (quantity & amount).
    """
    try:
        return await svc.get_pool_status(pool_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
