"""Subrace feature read endpoint: list SUBRACE-source features."""

from fastapi import APIRouter

from app.core.types import EntityIdPath
from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.subraces.dependencies import SubraceFeaturesDep

router = APIRouter()


@router.get(
    "/{subrace_id:int}/features",
    response_model=list[NestedFeatureResponse],
    summary="List a subrace's features",
    responses={404: {"description": "No subrace exists with the given ID."}},
)
async def list_features(
    subrace_id: EntityIdPath,
    subrace_service: SubraceFeaturesDep,
):
    """Return every feature owned by the subrace (``source_type: SUBRACE``). Open endpoint."""

    return await subrace_service.list_features(subrace_id)
