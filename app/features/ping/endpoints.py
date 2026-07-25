import time

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def ping():
    return {"ping": "pong", "timestamp": time.time(), "status": "healthy"}
