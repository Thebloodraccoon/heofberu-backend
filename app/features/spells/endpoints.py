from fastapi import APIRouter, Body

from app.core.dependencies import GmUserDep, SpellServiceDep
from app.features.spells.schemas import (
    ClassAvailabilityUpdate,
    RaceAvailabilityUpdate,
    SpellBriefResponse,
    SpellCreate,
    SpellResponse,
    SpellUpdate,
)

router = APIRouter(prefix="/spells", tags=["Spells"])


@router.get(
    "/",
    response_model=list[SpellResponse],
    summary="List spells (full detail)",
)
def get_spells(
    spell_service: SpellServiceDep,
    skip: int = 0,
    limit: int = 100,
    school: str | None = None,
    level: str | None = None,
    search: str | None = None,
):
    """
    Return a paginated list of spell, with full detail — including
    available classes and available races.

    Open endpoint, no authentication required.

    `school` and `level` are exact matches (e.g. `school=EVOCATION`,
    `level=LEVEL_1`) and can be combined. `search` is a case-insensitive
    partial match against the spell name.

    For a lighter payload, use `GET /spells/brief` instead.
    """
    filters = {"school": school, "level": level}
    return spell_service.get_all(skip=skip, limit=limit, filters=filters, search=search)


@router.get(
    "/brief",
    response_model=list[SpellBriefResponse],
    summary="List spells (minimal fields)",
)
def get_spells_brief(
    spell_service: SpellServiceDep,
    skip: int = 0,
    limit: int = 100,
    school: str | None = None,
    level: str | None = None,
    search: str | None = None,
):
    """
    Return a paginated list of spells with only `id`, `name`, `school`,
    `level`, `is_homebrew`, `available_classes`, and `available_races`.

    Open endpoint, no authentication required.

    `school` and `level` are exact matches and can be combined; `search`
    is a case-insensitive partial match against the spell name — same
    semantics as `GET /spells/`.

    Does not include components, description, dice, or other heavier
    detail fields — use `GET /spells/{spell_id}` for the full record.
    Intended for dropdowns, tables, and similar listing UI where the full
    payload is unnecessary but availability still needs to be shown or
    filtered on.
    """
    filters = {"school": school, "level": level}
    return spell_service.list_brief(skip=skip, limit=limit, filters=filters, search=search)


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
    Return a single spell by ID, with full detail — including available
    classes and available races.

    Open endpoint, no authentication required.
    """
    return spell_service.get_by_id(spell_id)


@router.post(
    "/",
    response_model=SpellResponse,
    status_code=201,
    summary="Create a spell",
    responses={
        400: {
            "description": "A spell with this name already exists, or an available_classes/available_races id is invalid."
        },
    },
)
def create_spell(
    spell_service: SpellServiceDep,
    _: GmUserDep,
    spell_data: SpellCreate = Body(
        openapi_examples={
            "minimal": {
                "summary": "Minimal — no attack roll, damage, or healing",
                "value": {
                    "name": "Mage Armor",
                    "school": "ABJURATION",
                    "level": "LEVEL_1",
                    "cast_time": "1 action",
                    "range_type": "TOUCH",
                    "has_verbal": True,
                    "has_somatic": True,
                    "has_material": True,
                    "is_material_consumed": False,
                    "material": "a piece of cured leather",
                    "duration": "8 hours",
                    "description": "You touch a willing creature who isn't wearing armor, and its base AC becomes 13 + its Dexterity modifier.",
                },
            },
            "damage_with_availability": {
                "summary": "Damage spell, restricted to specific classes",
                "description": "available_classes/available_races are optional — omit or leave empty for an unrestricted spell.",
                "value": {
                    "name": "Guiding Bolt",
                    "school": "EVOCATION",
                    "level": "LEVEL_1",
                    "cast_time": "1 action",
                    "range_type": "RANGED",
                    "range_value": 120,
                    "has_verbal": True,
                    "has_somatic": True,
                    "has_material": False,
                    "is_material_consumed": False,
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
                    "available_classes": [3, 5],
                },
            },
            "healing": {
                "summary": "Healing spell",
                "value": {
                    "name": "Cure Wounds",
                    "school": "EVOCATION",
                    "level": "LEVEL_1",
                    "cast_time": "1 action",
                    "range_type": "TOUCH",
                    "has_verbal": True,
                    "has_somatic": True,
                    "has_material": False,
                    "is_material_consumed": False,
                    "duration": "Instantaneous",
                    "description": "A creature you touch regains a number of hit points.",
                    "healing_target": "HP",
                    "healing_dice_count": 1,
                    "healing_dice_type": "D8",
                    "available_classes": [2, 3, 5, 7],
                },
            },
        },
    ),
):
    """
    Create a new spell. **GM only.**

    `available_classes` and `available_races` are optional. If provided,
    they're saved together with the spell in a single transaction — the
    spell is fully set up in one call instead of a `POST` followed by
    `PUT` calls. An empty (or omitted) list on either side means the
    spell is unrestricted for that dimension.
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
    are left as-is. Does not touch available classes or available races —
    use `PUT /spells/{spell_id}/classes` and `PUT /spells/{spell_id}/races`
    for those.
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
    """
    Delete a spell. **GM only.**

    Also removes its class/race availability links (cascade).
    """
    spell_service.delete(spell_id)
    return None


@router.put(
    "/{spell_id}/classes",
    response_model=SpellResponse,
    summary="Replace a spell's available classes",
    responses={
        400: {"description": "One or more class IDs don't correspond to an existing class."},
        404: {"description": "No spell exists with the given ID."},
    },
)
def set_spell_classes(
    spell_id: int,
    spell_service: SpellServiceDep,
    _: GmUserDep,
    data: ClassAvailabilityUpdate = Body(
        openapi_examples={
            "replace": {
                "summary": "Restrict to two classes",
                "value": {"class_ids": [2, 5]},
            },
            "clear": {
                "summary": "Clear restriction — unrestricted for all classes",
                "value": {"class_ids": []},
            },
        },
    ),
):
    """
    Replace the set of classes a spell is available to. **GM only.**

    Full replace, not merge: the list in the request body becomes the
    complete set of classes for this spell — any class not included is
    removed. Send an empty list to clear the restriction (spell becomes
    available to every class).
    """
    return spell_service.set_classes(spell_id, data)


@router.put(
    "/{spell_id}/races",
    response_model=SpellResponse,
    summary="Replace a spell's available races",
    responses={
        400: {"description": "One or more race IDs don't correspond to an existing race."},
        404: {"description": "No spell exists with the given ID."},
    },
)
def set_spell_races(
    spell_id: int,
    spell_service: SpellServiceDep,
    _: GmUserDep,
    data: RaceAvailabilityUpdate = Body(
        openapi_examples={
            "replace": {
                "summary": "Restrict to two races (e.g. innate racial spellcasting)",
                "value": {"race_ids": [3, 8]},
            },
            "clear": {
                "summary": "Clear restriction — unrestricted for all races",
                "value": {"race_ids": []},
            },
        },
    ),
):
    """
    Replace the set of races a spell is available to. **GM only.**

    Full replace, not merge: the list in the request body becomes the
    complete set of races for this spell — any race not included is
    removed. Send an empty list to clear the restriction (spell becomes
    available to every race).
    """
    return spell_service.set_races(spell_id, data)
