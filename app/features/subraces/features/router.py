"""
Subrace feature read endpoint: list SUBRACE-source features.

Write endpoints (POST/PATCH/DELETE) have been removed — features are
managed centrally through the features catalog.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.subraces.dependencies import SubraceFeaturesDep

router = APIRouter()


@router.get(
    "/{subrace_id:int}/features",
    response_model=list[NestedFeatureResponse],
    summary="List a subrace's features",
    responses={404: {"description": "No subrace exists with the given ID under this race."}},
)
async def list_features(
    subrace_id: int,
    race_service: SubraceFeaturesDep,
):
    """Return every feature owned by the subrace (``source_type: SUBRACE``). Open endpoint."""

    return await race_service.list_features()
