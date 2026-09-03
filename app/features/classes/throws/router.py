"""Class saving-throws endpoint (query-style ``class_id``)."""

from typing import Annotated

from fastapi import APIRouter, Body

from app.features.classes.dependencies import ClassThrowsDep
from app.features.classes.schemas import ClassResponse, SavingThrowsUpdate
from app.features.users.security import GmUserDep

router = APIRouter()


@router.put(
    "/{class_id:int}/saving-throws",
    response_model=ClassResponse,
    summary="Replace a class's saving throws",
    responses={
        404: {"description": "No class exists with the given ID."},
    },
)
async def set_class_saving_throws(
    class_id: int,
    data: Annotated[
        SavingThrowsUpdate,
        Body(
            openapi_examples={
                "replace": {
                    "summary": "Replace with two saving throws",
                    "value": {"saving_throws": ["STR", "CON"]},
                },
                "clear": {
                    "summary": "Clear all saving throws",
                    "value": {"saving_throws": []},
                },
            },
        ),
    ],
    class_service: ClassThrowsDep,
    _: GmUserDep,
):
    """
    Replace all saving throw proficiencies for a class. **GM only.**

    Full replace: any throw not included is removed.
    """

    return await class_service.set_saving_throws(class_id, data)
