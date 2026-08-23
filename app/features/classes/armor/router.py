"""Class armor-proficiencies endpoint."""

from fastapi import APIRouter, Body

from app.features.classes.dependencies import ClassArmorDep
from app.features.classes.schemas import ArmorProficienciesUpdate, ClassResponse
from app.features.users.security import GmUserDep

router = APIRouter()


@router.put(
    "/{class_id}/armor-proficiencies",
    response_model=ClassResponse,
    summary="Replace a class's armor proficiencies",
    responses={
        404: {"description": "No class exists with the given ID."},
    },
)
async def set_class_armor_proficiencies(
    class_id: int,
    class_service: ClassArmorDep,
    _: GmUserDep,
    data: ArmorProficienciesUpdate = Body(
        openapi_examples={
            "fighter": {
                "summary": "Fighter — all armor + shields",
                "value": {"armor_proficiencies": ["LIGHT", "MEDIUM", "HEAVY", "SHIELD"]},
            },
            "clear": {
                "summary": "Clear all armor proficiencies",
                "value": {"armor_proficiencies": []},
            },
        },
    ),
):
    """
    Replace all armor proficiencies for a class. **GM only.**

    Full replace, not merge: the list in the request body becomes the
    complete set of armor proficiencies for this class — any armor type
    not included is removed. Send an empty list to clear them all.
    """

    return await class_service.set_armor_proficiencies(class_id, data)
