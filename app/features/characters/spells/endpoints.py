"""Character spell endpoints: slots, known spells, and learning."""

from fastapi import APIRouter, Body, status

from app.core.dependencies import CharacterSpellServiceDep, CurrentUserDep
from app.features.characters.spells.schemas import (
    CharacterSpellAdd,
    CharacterSpellResponse,
    SpellSlotResponse,
    SpellSlotUpdate,
)

router = APIRouter(tags=["Characters Spells"])


@router.get(
    "/{character_id}/spell-slots",
    response_model=list[SpellSlotResponse],
    summary="List a character's spell slots",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_spell_slots(
    character_id: int, spell_service: CharacterSpellServiceDep, current_user: CurrentUserDep
):
    """Get all spell slot entries (by level) for a character."""

    return await spell_service.get_spell_slots(character_id, current_user)


@router.patch(
    "/{character_id}/spell-slots",
    response_model=SpellSlotResponse,
    summary="Spend or restore spell slots at a level",
    responses={
        400: {"description": "`used` would be negative or exceed `total`."},
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def update_character_spell_slot(
    character_id: int,
    spell_service: CharacterSpellServiceDep,
    current_user: CurrentUserDep,
    data: SpellSlotUpdate = Body(
        openapi_examples={
            "spend": {
                "summary": "Spend a slot (cast a level-3 spell)",
                "value": {"level": "LEVEL_3", "used": 2},
            },
            "restore": {
                "summary": "Restore all slots at a level",
                "value": {"level": "LEVEL_3", "used": 0},
            },
        },
    ),
):
    """
    Spend or restore spell slots at a given level.

    Only ``used`` is editable. Slot ``total`` is always derived from the
    character's class/level spell-slot progression (applied on create and
    re-applied on level-up/class change) — it is not client-settable, so
    a player cannot grant themselves extra slots.
    """

    return await spell_service.update_spell_slot(character_id, data, current_user)


@router.get(
    "/{character_id}/spells",
    response_model=list[CharacterSpellResponse],
    summary="List a character's known spells",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_spells(character_id: int, spell_service: CharacterSpellServiceDep, current_user: CurrentUserDep):
    """List all spells known by the character."""

    return await spell_service.get_known_spells(character_id, current_user)


@router.post(
    "/{character_id}/spells",
    response_model=CharacterSpellResponse,
    status_code=201,
    summary="Add a spell to a character's known spells",
    responses={
        400: {
            "description": (
                "The spell's class/race restrictions exclude this character, or the "
                "character already knows as many spells of this level as they have slots for."
            )
        },
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character or spell exists with the given ID."},
        409: {"description": "The character already knows this spell."},
    },
)
async def add_character_spell(
    character_id: int,
    data: CharacterSpellAdd,
    spell_service: CharacterSpellServiceDep,
    current_user: CurrentUserDep,
):
    """
    Add a spell to the character's known spells (e.g. `{"spell_id": 5}`).

    There is no separate "prepared" state — knowing a spell is having it
    ready to cast. Choosing a spell is capped by the character's spell
    slot totals: a character may know at most as many spells of a given
    level as they have slots of that level. To swap a known spell for a
    different one, remove the old one first to free up its slot.
    """

    return await spell_service.add_known_spell(character_id, data, current_user)


@router.delete(
    "/{character_id}/spells/{spell_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a spell from a character's known spells",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID, or the character does not know this spell."},
    },
)
async def remove_character_spell(
    character_id: int,
    spell_id: int,
    spell_service: CharacterSpellServiceDep,
    current_user: CurrentUserDep,
):
    """Remove a spell from the character's known spells, freeing up its slot."""

    await spell_service.remove_known_spell(character_id, spell_id, current_user)
    return None
