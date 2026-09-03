"""Subclass feature read endpoint: list SUBCLASS-source features (writes go through the features catalog)."""

from fastapi import APIRouter

from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.subclasses.dependencies import SubclassFeaturesDep

router = APIRouter()


@router.get(
    "/{subclass_id:int}/features",
    response_model=list[NestedFeatureResponse],
    summary="List a subclass's features",
    responses={404: {"description": "Class or subclass not found."}},
)
async def list_subclass_features(
    subclass_id: int,
    class_service: SubclassFeaturesDep,
):
    """Return every SUBCLASS-source feature of the subclass. Open endpoint."""

    return await class_service.list_features(subclass_id)
