"""Admin endpoints (found-father only)."""

from fastapi import APIRouter, status

from app.core.cache import flush_all
from app.features.users.security import FounderDep

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.delete(
    "/cache",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Flush the entire cache",
    description=(
        "Delete every cached entry across all namespaces (best-effort). "
        "Only keys under the app's cache prefix are removed; the JWT "
        "blacklist and other Redis keys are preserved."
    ),
)
async def flush_cache(_: FounderDep) -> None:
    """
    Flush the whole cache under the app's prefix. **Founder only.**
    JWT blacklist and other non-app Redis keys are left untouched.
    """

    await flush_all()
    return None
