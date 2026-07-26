from fastapi import APIRouter, status

from app.core.dependencies import CharacterServiceDep, CurrentUserDep
from app.features.characters.schemas import (
    AttackCreate,
    AttackResponse,
    AttackUpdate,
    CharacterCreate,
    CharacterResponse,
    CharacterSpellAdd,
    CharacterSpellPrepareUpdate,
    CharacterSpellResponse,
    CharacterUpdate,
    HpUpdate,
    RestRequest,
    RollAttackRequest,
    RollAttackResponse,
    RollCheckRequest,
    RollCheckResponse,
    SavingThrowProficienciesUpdate,
    SkillProficienciesUpdate,
    SpellSlotResponse,
    SpellSlotUpdate,
)

router = APIRouter()


@router.get("/", response_model=list[CharacterResponse])
def get_characters(character_service: CharacterServiceDep, current_user: CurrentUserDep):
    """GM gets every character. Players get only their own."""
    return character_service.get_characters(current_user)


@router.get("/{character_id}", response_model=CharacterResponse)
def get_character(character_id: int, character_service: CharacterServiceDep, current_user: CurrentUserDep):
    """GM can view any character. Players can only view their own."""
    return character_service.get_character(character_id, current_user)


@router.post("/", response_model=CharacterResponse, status_code=201)
def create_character(
    character_data: CharacterCreate, character_service: CharacterServiceDep, current_user: CurrentUserDep
):
    """Any authenticated user (GM or player) can create a character, owned by themselves."""
    return character_service.create_character(character_data, current_user)


@router.patch("/{character_id}", response_model=CharacterResponse)
def update_character(
    character_id: int,
    update_data: CharacterUpdate,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """GM can update any character. Players can only update their own."""
    return character_service.update_character(character_id, update_data, current_user)


@router.delete("/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character(
    character_id: int, character_service: CharacterServiceDep, current_user: CurrentUserDep
):
    """GM can delete any character. Players can only delete their own."""
    character_service.delete_character(character_id, current_user)
    return None


@router.patch("/{character_id}/hp", response_model=CharacterResponse)
def update_character_hp(
    character_id: int,
    data: HpUpdate,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """Apply damage/healing via a relative delta, or set absolute HP values.

    current_hp is clamped to [0, max_hp]; temp_hp is clamped to >= 0.
    """
    return character_service.update_hp(character_id, data, current_user)


@router.put("/{character_id}/skills", response_model=CharacterResponse)
def set_character_skill_proficiencies(
    character_id: int,
    data: SkillProficienciesUpdate,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """Fully replace a character's skill proficiencies (with expertise flags)."""
    return character_service.set_skill_proficiencies(character_id, data, current_user)


@router.put("/{character_id}/saving-throws", response_model=CharacterResponse)
def set_character_saving_throws(
    character_id: int,
    data: SavingThrowProficienciesUpdate,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """Fully replace a character's saving throw proficiencies."""
    return character_service.set_saving_throw_proficiencies(character_id, data, current_user)


@router.get("/{character_id}/spell-slots", response_model=list[SpellSlotResponse])
def get_character_spell_slots(
    character_id: int, character_service: CharacterServiceDep, current_user: CurrentUserDep
):
    """Get all spell slot entries (by level) for a character."""
    return character_service.get_spell_slots(character_id, current_user)


@router.patch("/{character_id}/spell-slots", response_model=SpellSlotResponse)
def update_character_spell_slot(
    character_id: int,
    data: SpellSlotUpdate,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """Spend or restore spell slots at a given level (e.g. {"level": "level_3", "used": 2}).

    Creates the slot entry if it doesn't exist yet (e.g. to grant a
    character's initial slots at a level).
    """
    return character_service.update_spell_slot(character_id, data, current_user)


@router.post("/{character_id}/rest", response_model=CharacterResponse)
def rest_character(
    character_id: int,
    data: RestRequest,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """Take a short or long rest ({"type": "long"} or {"type": "short"}).

    Long rest: restores current_hp to max_hp, clears temp_hp, and resets all
    spell slots. Short rest: currently a no-op placeholder (see service
    docstring) pending hit-dice tracking.
    """
    return character_service.rest(character_id, data, current_user)


@router.get("/{character_id}/spells", response_model=list[CharacterSpellResponse])
def get_character_spells(
    character_id: int, character_service: CharacterServiceDep, current_user: CurrentUserDep
):
    """List all spells known by the character, with prepared status."""
    return character_service.get_known_spells(character_id, current_user)


@router.post("/{character_id}/spells", response_model=CharacterSpellResponse, status_code=201)
def add_character_spell(
    character_id: int,
    data: CharacterSpellAdd,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """Add a spell to the character's known spells (e.g. {"spell_id": 5})."""
    return character_service.add_known_spell(character_id, data, current_user)


@router.delete("/{character_id}/spells/{spell_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_character_spell(
    character_id: int,
    spell_id: int,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """Remove a spell from the character's known spells."""
    character_service.remove_known_spell(character_id, spell_id, current_user)
    return None


@router.patch("/{character_id}/spells/{spell_id}", response_model=CharacterSpellResponse)
def update_character_spell_prepared(
    character_id: int,
    spell_id: int,
    data: CharacterSpellPrepareUpdate,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """Toggle whether a known spell is currently prepared."""
    return character_service.set_spell_prepared(character_id, spell_id, data, current_user)


@router.get("/{character_id}/attacks", response_model=list[AttackResponse])
def get_character_attacks(
    character_id: int, character_service: CharacterServiceDep, current_user: CurrentUserDep
):
    """List all attacks belonging to a character."""
    return character_service.get_attacks(character_id, current_user)


@router.post("/{character_id}/attacks", response_model=AttackResponse, status_code=201)
def create_character_attack(
    character_id: int,
    data: AttackCreate,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """Add a new attack/weapon entry to a character."""
    return character_service.create_attack(character_id, data, current_user)


@router.patch("/{character_id}/attacks/{attack_id}", response_model=AttackResponse)
def update_character_attack(
    character_id: int,
    attack_id: int,
    data: AttackUpdate,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """Update an existing attack/weapon entry."""
    return character_service.update_attack(character_id, attack_id, data, current_user)


@router.delete("/{character_id}/attacks/{attack_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_character_attack(
    character_id: int,
    attack_id: int,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """Remove an attack/weapon entry from a character."""
    character_service.delete_attack(character_id, attack_id, current_user)
    return None


@router.post("/{character_id}/roll-check", response_model=RollCheckResponse)
def roll_character_check(
    character_id: int,
    data: RollCheckRequest,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """Roll a skill check ({"skill_id": 3}) or a raw ability check/saving throw
    ({"ability": "DEX", "check_type": "save"}). Applies the character's
    ability modifier and, where proficient, their proficiency bonus.
    """
    return character_service.roll_check(character_id, data, current_user)


@router.post("/{character_id}/roll-attack", response_model=RollAttackResponse)
def roll_character_attack(
    character_id: int,
    data: RollAttackRequest,
    character_service: CharacterServiceDep,
    current_user: CurrentUserDep,
):
    """Roll an attack ({"attack_id": 7}): computes the attack roll (with
    advantage-free d20, ability modifier, proficiency, and attack bonus) and,
    on a hit, the corresponding damage roll (doubling dice on a natural 20).
    """
    return character_service.roll_attack(character_id, data, current_user)