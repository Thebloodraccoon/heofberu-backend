import time

from fastapi import APIRouter

router = APIRouter(prefix="/ping", tags=["Health Check"])


@router.get("/")
def ping():
    return {"ping": "pong", "timestamp": time.time(), "status": "healthy"}
