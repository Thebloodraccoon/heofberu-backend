"""Class weapon-proficiencies endpoint (query-style ``class_id``)."""

from typing import Annotated

from fastapi import APIRouter, Body, Query

from app.features.classes.dependencies import ClassWeaponsDep
from app.features.classes.schemas import ClassResponse, WeaponProficienciesUpdate
from app.features.users.security import GmUserDep

router = APIRouter()


@router.put(
    "/{class_id:int}/weapon-proficiencies",
    response_model=ClassResponse,
    summary="Replace a class's weapon proficiencies",
    responses={
        404: {"description": "No class exists with the given ID."},
    },
)
async def set_class_weapon_proficiencies(
    class_id: int,
    data: Annotated[
        WeaponProficienciesUpdate,
        Body(
            openapi_examples={
                "fighter": {
                    "summary": "Fighter — simple + martial weapons",
                    "value": {"weapon_proficiencies": ["SIMPLE", "MARTIAL"]},
                },
                "wizard": {
                    "summary": "Wizard — simple weapons only",
                    "value": {"weapon_proficiencies": ["SIMPLE"]},
                },
                "clear": {
                    "summary": "Clear all weapon proficiencies",
                    "value": {"weapon_proficiencies": []},
                },
            },
        ),
    ],
    class_service: ClassWeaponsDep,
    _: GmUserDep,
):
    """
    Replace all weapon proficiencies for a class. **GM only.**

    Full replace: any weapon category not included is removed.
    """

    return await class_service.set_weapon_proficiencies(class_id, data)
