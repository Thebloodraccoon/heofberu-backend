"""Health-check endpoints: liveness (``/ping``) and readiness (``/ready``)."""

import logging
import time

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.db import DatabaseDep
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health Check"])


@router.get("/ping", summary="Liveness check")
async def ping():
    """
    Lightweight liveness response. Open endpoint —
    used by load balancers and uptime probes, no external services.
    """

    return {"ping": "pong", "timestamp": time.time(), "status": "healthy"}


@router.get(
    "/ready",
    summary="Readiness check",
    responses={503: {"description": "The database or Redis is unreachable."}},
)
async def ready(db: DatabaseDep):
    """
    Readiness: the database answers ``SELECT 1`` and both Redis instances (cache, auth state) answer ``PING``.

    Open endpoint for orchestrators; returns 503 with the per-dependency result when any check fails (the cause is
    logged, never returned).
    """

    checks = {
        "database": await _check(_ping_database(db)),
        "redis": await _check(_ping_redis(settings.get_redis)),
        "auth_redis": await _check(_ping_redis(settings.get_auth_redis)),
    }

    healthy = all(checks.values())
    results = {name: "ok" if passed else "fail" for name, passed in checks.items()}
    body = {"status": "ready" if healthy else "unavailable", "checks": results}
    return JSONResponse(body, status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE)


async def _ping_database(db: DatabaseDep) -> None:
    await db.execute(text("SELECT 1"))


async def _ping_redis(get_client) -> None:
    async with get_client() as redis:
        await redis.ping()


async def _check(probe) -> bool:
    try:
        await probe
    except Exception:  # noqa: BLE001 - any failure means "not ready"
        logger.warning("Readiness check failed", exc_info=True)
        return False

    return True
