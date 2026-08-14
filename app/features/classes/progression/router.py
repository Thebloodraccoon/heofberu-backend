"""Class progression endpoints: spell-slot table and full 1-20 progression."""

from fastapi import APIRouter, Body

from app.core.security.dependencies import GmUserDep
from app.features.classes.dependencies import ClassProgressionDep
from app.features.classes.schemas import (
    ClassProgressionResponse,
    ClassResponse,
    SpellSlotProgressionUpdate,
)

router = APIRouter()


@router.put(
    "/{class_id}/spell-slots/{class_level}",
    response_model=ClassResponse,
    summary="Replace a class's spell slots at a given class level",
    responses={
        400: {"description": "class_level is outside the valid 1-20 range."},
        404: {"description": "No class exists with the given ID."},
    },
)
async def set_class_spell_slots(
    class_id: int,
    class_level: int,
    class_service: ClassProgressionDep,
    _: GmUserDep,
    data: SpellSlotProgressionUpdate = Body(
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
):
    """
    Replace the spell slots a class grants at a single `class_level`.
    **GM only.**

    Full replace, not merge, scoped to this `class_level`: the
    `spell_level`/`slots` pairs in the request body become the complete
    set of slots granted at this level — any `spell_level` not included
    is reset to 0. Other class levels are untouched; call this endpoint
    once per level to build up the full progression table.

    No check is made that the class has a `spellcasting_ability` —
    progressions can be set on any class, including to support
    multiclass-style slot tables.
    """

    return await class_service.set_spell_slots(class_id, class_level, data)


@router.get(
    "/{class_id}/progression",
    response_model=ClassProgressionResponse,
    summary="Get the full 1-20 progression table",
    responses={404: {"description": "No class exists with the given ID."}},
)
async def get_class_progression(class_id: int, class_service: ClassProgressionDep):
    """
    Return the full level 1-20 progression table for a class.

    Each row contains:
    - ``level`` and ``proficiency_bonus``
    - ``spell_slots``: ``{spell_level: slots}`` (only non-zero entries)
    - ``class_features``: CLASS-source features gained at this level
    - ``subclass_features``: SUBCLASS-source features gained at this level
      (from all subclasses — useful for showing "subclass feature here")

    Open endpoint.
    """

    return await class_service.get_progression(class_id)
