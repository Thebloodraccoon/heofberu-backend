"""Class progression endpoints: spell-slot table and full 1-20 progression (query-style IDs)."""

from typing import Annotated

from fastapi import APIRouter, Body, Query

from app.features.auth.dependencies import GmUserDep
from app.features.classes.crud.schemas import ClassResponse
from app.features.classes.dependencies import ClassProgressionDep
from app.features.classes.progression.schemas import ClassProgressionResponse, SpellSlotProgressionUpdate

router = APIRouter()


@router.put(
    "/{class_id:int}/spell-slots",
    response_model=ClassResponse,
    summary="Replace a class's spell slots at a given class level",
    responses={
        404: {"description": "No class exists with the given ID."},
        422: {"description": "class_level is outside the valid 1-20 range, or a slot entry is invalid."},
    },
)
async def set_class_spell_slots(
    class_id: int,
    class_level: Annotated[int, Query(ge=1, le=20, description="Class level the slots apply to (1-20).")],
    data: Annotated[
        SpellSlotProgressionUpdate,
        Body(
            openapi_examples={
                "level_5_wizard": {
                    "summary": "Level 5 Wizard — 3 first-level, 3 second-level, 2 third-level slots",
                    "value": {
                        "slots": [
                            {"spell_level": "LEVEL_1", "slots": 3},
                            {"spell_level": "LEVEL_2", "slots": 3},
                            {"spell_level": "LEVEL_3", "slots": 2},
                        ]
                    },
                },
                "clear": {
                    "summary": "Clear all slots at this class level",
                    "value": {"slots": []},
                },
            },
        ),
    ],
    class_service: ClassProgressionDep,
    _: GmUserDep,
):
    """
    Replace the spell slots a class grants at a single `class_level`.
    **GM only.**

    Full replace scoped to this `class_level`: any `spell_level` not
    included is reset to 0. Other levels are untouched.
    """

    return await class_service.set_spell_slots(class_id, class_level, data)


@router.get(
    "/{class_id:int}/progression",
    response_model=ClassProgressionResponse,
    summary="Get the full 1-20 progression table",
    responses={404: {"description": "No class exists with the given ID."}},
)
async def get_class_progression(class_id: int, class_service: ClassProgressionDep):
    """
    Return the full 1-20 progression table for a class, with spell slots
    and class/subclass features per level (subclass features carry their
    `subclass_id`). Cached under the `classes` namespace.

    Open endpoint.
    """

    return await class_service.get_progression(class_id)
