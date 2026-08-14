"""
Assembled ``/spells`` router.

Each capability sub-router declares no prefix of its own; the ``/spells``
prefix is applied here via ``include_router(..., prefix=...)`` so
empty-path routes (``GET ""`` etc.) resolve to ``/spells``. The mounted
surface exposes the exact same paths as the previous monolithic endpoints
package.
"""

from fastapi import APIRouter

from app.features.spells.availability.router import router as availability_router
from app.features.spells.crud.router import router as crud_router

router = APIRouter()

router.include_router(crud_router, prefix="/spells", tags=["Spells"])
router.include_router(availability_router, prefix="/spells", tags=["Spells"])
