from fastapi import APIRouter, status

from app.core.dependencies import CharacterSpellServiceDep, CurrentUserDep
from app.features.characters.spells.schemas import (
    CharacterSpellAdd,
    CharacterSpellPrepareUpdate,
    CharacterSpellResponse,
    SpellSlotResponse,
    SpellSlotUpdate,
)

router = APIRouter(prefix="/characters", tags=["Characters"])


@router.get("/{character_id}/spell-slots", response_model=list[SpellSlotResponse])
def get_character_spell_slots(character_id: int, spell_service: CharacterSpellServiceDep, current_user: CurrentUserDep):
    """Get all spell slot entries (by level) for a character."""
    return spell_service.get_spell_slots(character_id, current_user)


@router.patch("/{character_id}/spell-slots", response_model=SpellSlotResponse)
def update_character_spell_slot(
    character_id: int,
    data: SpellSlotUpdate,
    spell_service: CharacterSpellServiceDep,
    current_user: CurrentUserDep,
):
    """
    Spend or restore spell slots at a given level (e.g. {"level": "level_3", "used": 2}).

    Creates the slot entry if it doesn't exist yet (e.g. to grant a
    character's initial slots at a level).
    """
    return spell_service.update_spell_slot(character_id, data, current_user)


@router.get("/{character_id}/spells", response_model=list[CharacterSpellResponse])
def get_character_spells(character_id: int, spell_service: CharacterSpellServiceDep, current_user: CurrentUserDep):
    """List all spells known by the character, with prepared status."""
    return spell_service.get_known_spells(character_id, current_user)


@router.post("/{character_id}/spells", response_model=CharacterSpellResponse, status_code=201)
def add_character_spell(
    character_id: int,
    data: CharacterSpellAdd,
    spell_service: CharacterSpellServiceDep,
    current_user: CurrentUserDep,
):
    """Add a spell to the character's known spells (e.g. {"spell_id": 5})."""
    return spell_service.add_known_spell(character_id, data, current_user)


@router.delete("/{character_id}/spells/{spell_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_character_spell(
    character_id: int,
    spell_id: int,
    spell_service: CharacterSpellServiceDep,
    current_user: CurrentUserDep,
):
    """Remove a spell from the character's known spells."""
    spell_service.remove_known_spell(character_id, spell_id, current_user)
    return None


@router.patch("/{character_id}/spells/{spell_id}", response_model=CharacterSpellResponse)
def update_character_spell_prepared(
    character_id: int,
    spell_id: int,
    data: CharacterSpellPrepareUpdate,
    spell_service: CharacterSpellServiceDep,
    current_user: CurrentUserDep,
):
    """Toggle whether a known spell is currently prepared."""
    return spell_service.set_spell_prepared(character_id, spell_id, data, current_user)
