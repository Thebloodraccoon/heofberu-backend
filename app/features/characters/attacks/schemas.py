"""Schemas for a character's attacks."""

from pydantic import BaseModel, ConfigDict

from app.constants import AbilityScore, AttackType, DamageType, DiceType


class AttackBase(BaseModel):
    """Base attack fields shared by create and response schemas."""

    name: str
    attack_type: AttackType
    ability: AbilityScore
    is_proficient: bool = True

    bonus_attack: int = 0
    bonus_damage: int = 0

    damage_dice_count: int | None = None
    damage_dice_type: DiceType | None = None

    damage_type: DamageType | None = None
    range: str = ""
    notes: str = ""


class AttackCreate(AttackBase):
    """Payload for adding an attack to a character."""


class AttackUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    name: str | None = None
    attack_type: AttackType | None = None
    ability: AbilityScore | None = None
    is_proficient: bool | None = None

    bonus_attack: int | None = None
    bonus_damage: int | None = None
    damage_dice_count: int | None = None
    damage_dice_type: DiceType | None = None
    damage_type: DamageType | None = None
    range: str | None = None
    notes: str | None = None


class AttackResponse(AttackBase):
    """Full attack representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
