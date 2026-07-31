from pydantic import BaseModel, ConfigDict

from app.constants import AbilityScore, AttackType, DamageType, DiceType, SpellLevel, SpellRangeType, SpellSchool


class SpellBase(BaseModel):
    name: str
    school: SpellSchool
    level: SpellLevel

    cast_time: str
    range_type: SpellRangeType
    range_value: int | None = None

    components: str  # e.g. "VERBAL,SOMATIC,MATERIAL"
    material: str | None = None
    is_ritual: bool = False

    duration: str
    is_concentration: bool = False

    # None means the spell has no attack roll (e.g. a save-based or utility spell).
    attack_type: AttackType | None = None
    save_stat: AbilityScore | None = None
    damage_type: DamageType | None = None
    damage_dice_count: int | None = None  # e.g. 2
    damage_dice_type: DiceType | None = None  # e.g. D6 -> "2d6" combined

    description: str
    higher_levels: str | None = None


class SpellCreate(SpellBase):
    pass


class SpellUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    name: str | None = None
    school: SpellSchool | None = None
    level: SpellLevel | None = None
    cast_time: str | None = None
    range_type: SpellRangeType | None = None
    range_value: int | None = None
    components: str | None = None
    material: str | None = None
    is_ritual: bool | None = None
    duration: str | None = None
    is_concentration: bool | None = None
    attack_type: AttackType | None = None
    save_stat: AbilityScore | None = None
    damage_type: DamageType | None = None
    damage_dice_count: int | None = None
    damage_dice_type: DiceType | None = None
    description: str | None = None
    higher_levels: str | None = None


class SpellResponse(SpellBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_homebrew: bool
    created_by_id: int | None = None


class SpellBriefResponse(BaseModel):
    """Lightweight listing row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    school: SpellSchool
    level: SpellLevel
    is_homebrew: bool
