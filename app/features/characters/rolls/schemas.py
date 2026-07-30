from pydantic import BaseModel

from app.constants import AbilityScore


class RollCheckRequest(BaseModel):
    """
    Request a skill check or saving throw roll.

    Provide exactly one of `skill_id` (skill check) or `ability` (raw
    ability check or saving throw, depending on `check_type`).
    """

    skill_id: int | None = None
    ability: AbilityScore | None = None
    check_type: str = "check"  # "check" or "save"


class RollCheckResponse(BaseModel):
    d20_roll: int
    ability: AbilityScore
    ability_modifier: int
    proficiency_bonus: int
    is_proficient: bool
    total: int
    check_type: str
    skill_id: int | None = None


class RollAttackRequest(BaseModel):
    attack_id: int


class RollAttackResponse(BaseModel):
    attack_id: int
    attack_name: str
    d20_roll: int
    ability_modifier: int
    proficiency_bonus: int
    is_proficient: bool
    attack_total: int
    damage_dice: str
    damage_roll: int
    damage_modifier: int
    damage_total: int
    is_critical: bool
