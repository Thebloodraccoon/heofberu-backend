"""Race feature read endpoint: list RACE-source features for a race."""

from fastapi import APIRouter

from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.races.dependencies import RaceFeaturesDep

router = APIRouter()


@router.get(
    "/{race_id:int}/features",
    response_model=list[NestedFeatureResponse],
    summary="List a race's features",
    responses={404: {"description": "No race exists with the given ID."}},
)
async def list_features(race_id: int, race_service: RaceFeaturesDep):
    """Return every feature owned by the race (``source_type: RACE``). Open endpoint."""

    return await race_service.list_features(race_id)
