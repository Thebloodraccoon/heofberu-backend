"""Class feature read endpoint: list CLASS-source features (writes go through the features catalog)."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.features.classes.dependencies import ClassFeaturesDep
from app.features.features.crud.schemas import NestedFeatureResponse

router = APIRouter()


@router.get(
    "/{class_id:int}/features",
    response_model=list[NestedFeatureResponse],
    summary="List a class's features",
    responses={404: {"description": "No class exists with the given ID."}},
)
async def list_class_features(class_id: int, class_service: ClassFeaturesDep):
    """Return every CLASS-source feature of the class. Open endpoint."""

    return await class_service.list_features(class_id)
