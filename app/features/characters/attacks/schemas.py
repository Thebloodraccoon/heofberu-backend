"""Schemas for a character's attacks."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.constants import AbilityScore, AttackType, DamageType, DiceType
from app.features.characters.schemas import PatchModel

AttackName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
AttackRange = Annotated[str, Field(max_length=50)]
AttackNotes = Annotated[str, Field(max_length=5_000)]
AttackBonus = Annotated[int, Field(ge=-100, le=100)]
DiceCount = Annotated[int, Field(ge=1, le=100)]


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

    name: AttackName
    bonus_attack: AttackBonus = 0
    bonus_damage: AttackBonus = 0
    damage_dice_count: DiceCount | None = None
    range: AttackRange = ""
    notes: AttackNotes = ""


class AttackUpdate(PatchModel):
    """
    All fields optional — only provided fields are updated (PATCH semantics).
    An explicit ``null`` is rejected except for the nullable damage fields.
    """

    nullable_fields = frozenset({"damage_dice_count", "damage_dice_type", "damage_type"})

    name: AttackName | None = None
    attack_type: AttackType | None = None
    ability: AbilityScore | None = None
    is_proficient: bool | None = None
    bonus_attack: AttackBonus | None = None
    bonus_damage: AttackBonus | None = None
    damage_dice_count: DiceCount | None = None
    damage_dice_type: DiceType | None = None
    damage_type: DamageType | None = None
    range: AttackRange | None = None
    notes: AttackNotes | None = None


class AttackResponse(AttackBase):
    """Full attack representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
