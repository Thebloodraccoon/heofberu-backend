"""
Class weapon-proficiencies endpoint (query-style ID — the class is
identified by the required ``class_id`` query parameter).
"""

from typing import Annotated

from fastapi import APIRouter, Body, Query

from app.features.classes.dependencies import ClassWeaponsDep
from app.features.classes.schemas import ClassResponse, WeaponProficienciesUpdate
from app.features.users.security import GmUserDep

router = APIRouter()


@router.put(
    "/weapon-proficiencies",
    response_model=ClassResponse,
    summary="Replace a class's weapon proficiencies",
    responses={
        404: {"description": "No class exists with the given ID."},
    },
)
async def set_class_weapon_proficiencies(
    class_id: Annotated[int, Query(gt=0)],
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

    Full replace, not merge: the list in the request body becomes the
    complete set of weapon proficiencies for this class — any weapon
    category not included is removed. Send an empty list to clear them all.
    """

    return await class_service.set_weapon_proficiencies(class_id, data)
