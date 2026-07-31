from fastapi import APIRouter, Body

from app.core.dependencies import GmUserDep, SpellServiceDep
from app.features.spells.schemas import SpellBriefResponse, SpellCreate, SpellResponse, SpellUpdate

router = APIRouter(prefix="/spells", tags=["Spells"])


@router.get(
    "/",
    response_model=list[SpellResponse],
    summary="List spells (full detail)",
)
def get_spells(spell_service: SpellServiceDep, skip: int = 0, limit: int = 100):
    """
    Return a paginated list of spell, with full detail.

    Open endpoint, no authentication required.

    For a lighter payload, use `GET /spells/brief` instead.
    """
    return spell_service.get_all(skip=skip, limit=limit)


@router.get(
    "/brief",
    response_model=list[SpellBriefResponse],
    summary="List spells (minimal fields)",
)
def get_spells_brief(spell_service: SpellServiceDep, skip: int = 0, limit: int = 100):
    """
    Return a paginated list of spells with only `id`, `name`, `school`,
    `level`, and `is_homebrew`.

    Open endpoint, no authentication required.

    Does not include components, description, dice, or other detail
    fields — use `GET /spells/{spell_id}` for the full record. Intended
    for dropdowns, tables, and similar listing UI where the full payload
    is unnecessary.
    """
    return spell_service.list_brief(skip=skip, limit=limit)


@router.get(
    "/{spell_id}",
    response_model=SpellResponse,
    summary="Get a spell by ID",
    responses={
        404: {"description": "Spell with id not found."},
    },
)
def get_spell(spell_id: int, spell_service: SpellServiceDep):
    """
    Return a single spell by ID, with full detail.

    Open endpoint, no authentication required.
    """
    return spell_service.get_by_id(spell_id)


@router.post(
    "/",
    response_model=SpellResponse,
    status_code=201,
    summary="Create a spell",
    responses={
        400: {"description": "A spell with this name already exists."},
    },
)
def create_spell(
    spell_service: SpellServiceDep,
    _: GmUserDep,
    spell_data: SpellCreate = Body(
        openapi_examples={
            "minimal": {
                "summary": "Minimal — no attack roll or damage",
                "value": {
                    "name": "Mage Armor",
                    "school": "ABJURATION",
                    "level": "LEVEL_1",
                    "cast_time": "1 action",
                    "range_type": "TOUCH",
                    "components": "VERBAL,SOMATIC,MATERIAL",
                    "material": "a piece of cured leather",
                    "duration": "8 hours",
                    "description": "You touch a willing creature who isn't wearing armor, and its base AC becomes 13 + its Dexterity modifier.",
                },
            },
            "full": {
                "summary": "Full — every field shown, including optional ones",
                "description": "Every field the schema accepts, spelled out explicitly (nulls included) so it's clear what's available.",
                "value": {
                    "name": "Guiding Bolt",
                    "school": "EVOCATION",
                    "level": "LEVEL_1",
                    "cast_time": "1 action",
                    "range_type": "RANGED",
                    "range_value": 120,
                    "components": "VERBAL,SOMATIC",
                    "material": None,
                    "is_ritual": False,
                    "duration": "1 round",
                    "is_concentration": False,
                    "attack_type": "RANGED_ATTACK",
                    "save_stat": None,
                    "damage_type": "RADIANT",
                    "damage_dice_count": 4,
                    "damage_dice_type": "D6",
                    "description": "A flash of light streaks toward a creature of your choice within range. Make a ranged spell attack against the target. On a hit, the target takes 4d6 radiant damage, and the next attack roll made against this target before the end of your next turn has advantage.",
                    "higher_levels": "When you cast this spell using a spell slot of 2nd level or higher, the damage increases by 1d6 for each slot level above 1st.",
                },
            },
        },
    ),
):
    """
    Create a new spell. **GM only.**
    """
    return spell_service.create_spell(spell_data)


@router.patch(
    "/{spell_id}",
    response_model=SpellResponse,
    summary="Update a spell",
    responses={
        400: {"description": "Another spell already uses the requested name."},
        404: {"description": "No spell exists with the given ID."},
    },
)
def update_spell(spell_id: int, update_data: SpellUpdate, spell_service: SpellServiceDep, _: GmUserDep):
    """
    Partially update a spell. **GM only.**

    Only fields included in the request body are changed; omitted fields
    are left as-is.
    """
    return spell_service.update_spell(spell_id, update_data)


@router.delete(
    "/{spell_id}",
    status_code=204,
    summary="Delete a spell",
    responses={
        404: {"description": "No spell exists with the given ID."},
    },
)
def delete_spell(spell_id: int, spell_service: SpellServiceDep, _: GmUserDep):
    """Delete a spell. **GM only.**"""
    spell_service.delete(spell_id)
    return None
