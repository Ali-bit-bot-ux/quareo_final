"""
RetailPool AI v2.0 — FastAPI Application Entry Point.

Features:
  - Lifespan management (DB, Redis)
  - API Key middleware (MVP auth)
  - CORS
  - Health check
  - Pool & Scanner routers
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Security, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader

from retailpool.config import settings
from retailpool.database import engine
from retailpool.routers.pools import router as pools_router
from retailpool.routers.scanner import router as scanner_router
from retailpool.routers.documents import router as documents_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Lifespan — startup / shutdown hooks
# ═══════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup / shutdown hooks.

    NOTE: Database tables are managed by Alembic migrations.
    Run `alembic upgrade head` before starting the server.
    """
    logger.info("Starting RetailPool AI v2.0 ...")
    logger.info("Database: %s", settings.DATABASE_URL[:50] + "...")

    yield

    # Shutdown
    await engine.dispose()
    logger.info("RetailPool AI shut down.")


# ═══════════════════════════════════════════════════════════════════════════
# API Key Security (MVP — static token)
# ═══════════════════════════════════════════════════════════════════════════

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def get_api_key(
    api_key: str | None = Security(api_key_header),
) -> str:
    """Validate the static API key from request headers."""
    if api_key and api_key == settings.API_KEY:
        return api_key
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid or missing API key",
    )


# ═══════════════════════════════════════════════════════════════════════════
# FastAPI Application
# ═══════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="RetailPool AI v2.0",
    description=(
        "Omnichannel analytics & co-buying platform. "
        "Kaspi niche scanning + cooperative purchasing engine."
    ),
    version="2.0.0-mvp",
    lifespan=lifespan,
)

# CORS (allow all for MVP; restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(pools_router)
app.include_router(scanner_router)
app.include_router(documents_router)


# ── Health check (no auth required) ──────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check() -> dict:
    return {"status": "ok", "service": "retailpool-ai", "version": "2.0.0-mvp"}


# ── Protected endpoint example ──────────────────────────────────────────

@app.get("/protected", tags=["System"])
async def protected_route(api_key: str = Security(get_api_key)) -> dict:
    """Example protected endpoint — requires X-API-Key header."""
    return {"status": "authenticated", "message": "API key is valid"}
