"""Health-check endpoint."""

import time

from fastapi import APIRouter

router = APIRouter(prefix="/ping", tags=["Health Check"])


@router.get("", summary="Health check")
async def ping():
    """
    Lightweight liveness response. Open endpoint —
    used by load balancers and uptime probes, no external services.
    """

    return {"ping": "pong", "timestamp": time.time(), "status": "healthy"}
