from fastapi import APIRouter

from app.core.dependencies import CharacterRollServiceDep, CurrentUserDep
from app.features.characters.rolls.schemas import (
    RollAttackRequest,
    RollAttackResponse,
    RollCheckRequest,
    RollCheckResponse,
)

router = APIRouter(tags=["Characters Rolls"])


@router.post("/{character_id}/roll-check", response_model=RollCheckResponse)
def roll_character_check(
    character_id: int,
    data: RollCheckRequest,
    roll_service: CharacterRollServiceDep,
    current_user: CurrentUserDep,
):
    """
    Roll a skill check ({"skill_id": 3}) or a raw ability check/saving throw
    ({"ability": "DEX", "check_type": "save"}). Applies the character's
    ability modifier and, where proficient, their proficiency bonus.
    """
    return roll_service.roll_check(character_id, data, current_user)


@router.post("/{character_id}/roll-attack", response_model=RollAttackResponse)
def roll_character_attack(
    character_id: int,
    data: RollAttackRequest,
    roll_service: CharacterRollServiceDep,
    current_user: CurrentUserDep,
):
    """
    Roll an attack ({"attack_id": 7}): computes the attack roll (with
    advantage-free d20, ability modifier, proficiency, and attack bonus) and,
    on a hit, the corresponding damage roll (doubling dice on a natural 20).
    """
    return roll_service.roll_attack(character_id, data, current_user)
