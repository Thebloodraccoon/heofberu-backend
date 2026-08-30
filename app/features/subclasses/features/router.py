"""
Subclass feature read endpoint: list SUBCLASS-source features.

Write endpoints (POST/PATCH/DELETE) have been removed — features are
managed centrally through the features catalog.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.features.subclasses.dependencies import SubclassFeaturesDep
from app.features.features.crud.schemas import NestedFeatureResponse

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
