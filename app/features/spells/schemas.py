from pydantic import BaseModel, ConfigDict


class SpellBase(BaseModel):
    name: str
    school: str
    level: str  # e.g. CANTRIP, LEVEL_1..LEVEL_9

    cast_time: str
    range_type: str
    range_value: int | None = None

    components: str  # e.g. "VERBAL,SOMATIC,MATERIAL"
    material: str | None = None
    is_ritual: bool = False

    duration: str
    is_concentration: bool = False

    attack_type: str = "NONE"
    save_stat: str | None = None
    damage_type: str | None = None
    damage_dice: str | None = None

    description: str
    higher_levels: str | None = None


class SpellCreate(SpellBase):
    pass


class SpellUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    name: str | None = None
    school: str | None = None
    level: str | None = None
    cast_time: str | None = None
    range_type: str | None = None
    range_value: int | None = None
    components: str | None = None
    material: str | None = None
    is_ritual: bool | None = None
    duration: str | None = None
    is_concentration: bool | None = None
    attack_type: str | None = None
    save_stat: str | None = None
    damage_type: str | None = None
    damage_dice: str | None = None
    description: str | None = None
    higher_levels: str | None = None


class SpellResponse(SpellBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
