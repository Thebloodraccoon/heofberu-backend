"""Health-check endpoint."""

import time

from fastapi import APIRouter

router = APIRouter(prefix="/ping", tags=["Health Check"])


@router.get("")
def ping():
    """Return a lightweight liveness/health response."""
    return {"ping": "pong", "timestamp": time.time(), "status": "healthy"}
