from pydantic import BaseModel, ConfigDict

from app.constants import AbilityScore


class AttackBase(BaseModel):
    name: str
    attack_type: str  # e.g. MELEE, RANGED, SPELL
    ability: AbilityScore
    is_proficient: bool = True

    bonus_attack: int = 0
    bonus_damage: int = 0
    damage_dice: str = ""
    damage_type: str | None = None
    range: str = ""
    notes: str = ""


class AttackCreate(AttackBase):
    pass


class AttackUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    name: str | None = None
    attack_type: str | None = None
    ability: AbilityScore | None = None
    is_proficient: bool | None = None

    bonus_attack: int | None = None
    bonus_damage: int | None = None
    damage_dice: str | None = None
    damage_type: str | None = None
    range: str | None = None
    notes: str | None = None


class AttackResponse(AttackBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
