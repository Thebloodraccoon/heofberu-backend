from pydantic import BaseModel, ConfigDict

from app.features.spells.schemas import SpellResponse


class SpellSlotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    spell_level: str
    total: int
    used: int


class SpellSlotUpdate(BaseModel):
    """Update the used/total count for a single spell slot level."""

    level: str
    used: int | None = None
    total: int | None = None


class CharacterSpellAdd(BaseModel):
    spell_id: int


class CharacterSpellResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    spell_id: int
    spell: SpellResponse