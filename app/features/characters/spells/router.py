"""
Character spell endpoints: known spells with class-derived slot totals
(query-style IDs; ``app.features.characters.router`` applies the
``/characters`` prefix).
"""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.features.characters.dependencies import CharacterSpellServiceDep
from app.features.characters.spells.schemas import (
    CharacterSpellAdd,
    CharacterSpellResponse,
    CharacterSpellsResponse,
)
from app.features.users.security import CurrentUserDep

router = APIRouter()


@router.get(
    "/{character_id:int}/spells",
    response_model=CharacterSpellsResponse,
    summary="List a character's spell slots and known spells",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_spells(
    character_id: int,
    spell_service: CharacterSpellServiceDep,
    current_user: CurrentUserDep,
):
    """
    List the character's spellcasting picture in one payload: slot totals
    per level plus the known spells.

    Slot ``total`` is always derived from the class/level progression and
    is not client-settable; a level's total doubles as the cap on known
    spells of that level.
    """

    return await spell_service.get_spells(character_id, current_user)


@router.post(
    "/{character_id:int}/spells",
    response_model=CharacterSpellResponse,
    status_code=status.HTTP_201_CREATED,
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
    data: Annotated[
        CharacterSpellAdd,
        Body(
            openapi_examples={
                "add": {
                    "summary": "Learn the spell with ID 5",
                    "value": {"spell_id": 5},
                },
            }
        ),
    ],
    spell_service: CharacterSpellServiceDep,
    current_user: CurrentUserDep,
):
    """
    Add a spell to the character's known spells (e.g. `{"spell_id": 5}`).

    Knowing a spell IS having it ready — no "prepared" state and no slot
    spending. The character may know at most as many spells of a level as
    they have slots of that level; to swap, remove the old one first.
    """

    return await spell_service.add_known_spell(character_id, data, current_user)


@router.delete(
    "/{character_id:int}/spells",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a spell from a character's known spells",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID, or the character does not know this spell."},
    },
)
async def remove_character_spell(
    character_id: int,
    spell_id: Annotated[int, Query(gt=0)],
    spell_service: CharacterSpellServiceDep,
    current_user: CurrentUserDep,
):
    """Remove a spell from the character's known spells, freeing up its slot."""

    await spell_service.remove_known_spell(character_id, spell_id, current_user)
    return None
