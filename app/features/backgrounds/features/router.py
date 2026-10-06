"""Background feature read endpoint: list BACKGROUND-source features."""

from fastapi import APIRouter

from app.features.backgrounds.dependencies import BackgroundFeaturesDep
from app.features.features.crud.schemas import NestedFeatureResponse

router = APIRouter()


@router.get(
    "/features",
    response_model=list[NestedFeatureResponse],
    summary="List a background's features",
    responses={404: {"description": "No background exists with the given ID."}},
)
async def list_background_features(background_id: int, background_service: BackgroundFeaturesDep):
    """Return every feature owned by the background (``source_type: BACKGROUND``). Open endpoint."""

    return await background_service.list_features(background_id)
