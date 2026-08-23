"""Spell CRUD endpoints: paginated listing, get, create, update, delete."""

from fastapi import APIRouter, Body, Query

from app.constants import (
    AttackType,
    DamageType,
    HealingTarget,
    SpellCastTime,
    SpellDuration,
    SpellLevel,
    SpellRangeType,
    SpellSchool,
)
from app.core.base.service import Page
from app.features.spells.crud.schemas import (
    SpellCreate,
    SpellGetAllResponse,
    SpellResponse,
    SpellUpdate,
)
from app.features.spells.dependencies import SpellCrudDep
from app.features.users.security import FounderDep, GmUserDep

router = APIRouter()


@router.get(
    "",
    response_model=Page[SpellGetAllResponse],
    summary="List spells",
)
async def get_spells(
    spell_service: SpellCrudDep,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(10, ge=1, le=100, description="Page size"),
    school: SpellSchool | None = None,
    level: SpellLevel | None = None,
    cast_time: SpellCastTime | None = None,
    range_type: SpellRangeType | None = None,
    duration: SpellDuration | None = None,
    attack_type: AttackType | None = None,
    damage_type: DamageType | None = None,
    healing_target: HealingTarget | None = None,
    is_ritual: bool | None = None,
    is_concentration: bool | None = None,
    search: str | None = None,
):
    """
    Return a paginated list of spells with only `id`, `name`, `school`,
    `level`, and the four availability lists (`available_classes`,
    `available_subclasses`, `available_races`, `available_subraces`).

    Open endpoint, no authentication required.

    All filters below are exact matches and can be freely combined
    (AND'd together); `search` is a case-insensitive partial match
    against the spell name, combined with any filters.

    - `school` — e.g. `EVOCATION`
    - `level` — e.g. `LEVEL_1`, `CANTRIP`
    - `cast_time` — e.g. `ACTION`, `BONUS_ACTION`, `REACTION`
    - `range_type` — e.g. `RANGED`, `TOUCH`, `SELF`
    - `duration` — e.g. `INSTANTANEOUS`, `ONE_MINUTE`
    - `attack_type` — e.g. `RANGED_ATTACK`, `MELEE_ATTACK`
    - `damage_type` — e.g. `FIRE`, `RADIANT`
    - `healing_target` — e.g. `HP`, `TEMP_HP`
    - `is_ritual` / `is_concentration` — boolean flags

    Response is `{items, total, page, size}` — `total` is the count of
    matching spells across every page, not just this one.

    Does not include components, description, dice, or other heavier
    detail fields — use `GET /spells/{spell_id}` for the full record.
    """

    filters = {
        "school": school,
        "level": level,
        "cast_time": cast_time,
        "range_type": range_type,
        "duration": duration,
        "attack_type": attack_type,
        "damage_type": damage_type,
        "healing_target": healing_target,
        "is_ritual": is_ritual,
        "is_concentration": is_concentration,
    }
    return await spell_service.get_all(page=page, size=size, filters=filters, search=search)


@router.get(
    "/{spell_id}",
    response_model=SpellResponse,
    summary="Get a spell by ID",
    responses={
        404: {"description": "Spell with id not found."},
    },
)
async def get_spell(spell_id: int, spell_service: SpellCrudDep):
    """
    Return a single spell by ID, with full detail — including its
    availability lists (available classes, subclasses, races, subraces).

    Open endpoint, no authentication required.
    """

    return await spell_service.get_by_id(spell_id)


@router.post(
    "",
    response_model=SpellResponse,
    status_code=201,
    summary="Create a spell",
    responses={
        400: {"description": "A spell with this name already exists, or an availability id is invalid."},
    },
)
async def create_spell(
    spell_service: SpellCrudDep,
    _: GmUserDep,
    spell_data: SpellCreate = Body(
        openapi_examples={
            "minimal": {
                "summary": "Minimal — no attack roll, damage, or healing",
                "value": {
                    "name": "Mage Armor",
                    "school": "ABJURATION",
                    "level": "LEVEL_1",
                    "cast_time": "ACTION",
                    "range_type": "TOUCH",
                    "components": ["VERBAL", "SOMATIC", "MATERIAL"],
                    "is_material_consumed": False,
                    "material": "a piece of cured leather",
                    "duration": "EIGHT_HOURS",
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
                    "cast_time": "ACTION",
                    "range_type": "RANGED",
                    "range_value": 120,
                    "components": ["VERBAL", "SOMATIC"],
                    "is_material_consumed": False,
                    "material": None,
                    "is_ritual": False,
                    "duration": "ONE_ROUND",
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
                    "cast_time": "ACTION",
                    "range_type": "TOUCH",
                    "components": ["VERBAL", "SOMATIC"],
                    "is_material_consumed": False,
                    "duration": "INSTANTANEOUS",
                    "description": "A creature you touch regains a number of hit points.",
                    "healing_target": "HP",
                    "healing_dice_count": 1,
                    "healing_dice_type": "D8",
                    "available_classes": [2, 3, 5, 7],
                },
            },
            "ritual_utility": {
                "summary": "Ritual spell with no attack, damage, or healing",
                "description": "Shows is_ritual and a longer concentration duration.",
                "value": {
                    "name": "Detect Magic",
                    "school": "DIVINATION",
                    "level": "LEVEL_1",
                    "cast_time": "ACTION",
                    "range_type": "SELF",
                    "components": ["VERBAL", "SOMATIC"],
                    "is_material_consumed": False,
                    "is_ritual": True,
                    "duration": "TEN_MINUTES",
                    "is_concentration": True,
                    "description": "For the duration, you sense the presence of magic within 30 feet of you.",
                    "available_classes": [2, 3, 4, 7, 10, 11, 12],
                },
            },
            "reaction_spell": {
                "summary": "Reaction-cast spell",
                "description": "Shows cast_time=REACTION and a save-based (no attack roll) effect.",
                "value": {
                    "name": "Shield",
                    "school": "ABJURATION",
                    "level": "LEVEL_1",
                    "cast_time": "REACTION",
                    "range_type": "SELF",
                    "components": ["VERBAL", "SOMATIC"],
                    "is_material_consumed": False,
                    "duration": "ONE_ROUND",
                    "description": "An invisible barrier of magical force appears and protects you, granting +5 AC until the start of your next turn.",
                    "available_classes": [10, 12],
                },
            },
        },
    ),
):
    """
    Create a new spell. **GM only.**

    The four availability lists (`available_classes`,
    `available_subclasses`, `available_races`, `available_subraces`) are
    optional. If provided, they're saved together with the spell in a
    single transaction — the spell is fully set up in one call instead of
    a `POST` followed by `PUT` calls. An empty (or omitted) list means the
    spell is unrestricted for that dimension.
    """

    return await spell_service.create_spell(spell_data)


@router.patch(
    "/{spell_id}",
    response_model=SpellResponse,
    summary="Update a spell",
    responses={
        400: {"description": "Another spell already uses the requested name."},
        404: {"description": "No spell exists with the given ID."},
    },
)
async def update_spell(spell_id: int, update_data: SpellUpdate, spell_service: SpellCrudDep, _: GmUserDep):
    """
    Partially update a spell. **GM only.**

    Only fields included in the request body are changed; omitted fields
    are left as-is. Does not touch the availability lists — use
    `PUT /spells/{spell_id}/classes`, `PUT /spells/{spell_id}/subclasses`,
    `PUT /spells/{spell_id}/races`, and `PUT /spells/{spell_id}/subraces`
    for those.
    """

    return await spell_service.update(spell_id, update_data)


@router.delete(
    "/{spell_id}",
    status_code=204,
    summary="Delete a spell",
    responses={
        404: {"description": "No spell exists with the given ID."},
    },
)
async def delete_spell(spell_id: int, spell_service: SpellCrudDep, _: FounderDep):
    """
    Delete a spell. **Found-father only.**

    Also removes its class/race availability links (cascade).
    """

    await spell_service.delete(spell_id)
    return None
