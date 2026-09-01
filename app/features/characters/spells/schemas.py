"""Schemas for character spell slots and known spells."""

from pydantic import BaseModel, ConfigDict

from app.features.spells.crud.schemas import SpellResponse


class SpellSlotResponse(BaseModel):
    """
    A character's spell slot entry for one level. ``total`` always comes
    from the class/level spell-slot progression and doubles as the cap on
    how many spells of that level the character may know; slots are not
    spent, they are capacity for known spells.
    """

    model_config = ConfigDict(from_attributes=True)

    spell_level: str
    total: int


class CharacterSpellAdd(BaseModel):
    """Payload for adding a known spell to a character."""

    spell_id: int


class CharacterSpellResponse(BaseModel):
    """A known-spell entry returned on the character."""

    model_config = ConfigDict(from_attributes=True)

    spell_id: int
    spell: SpellResponse


class CharacterSpellsResponse(BaseModel):
    """
    Combined read model behind ``GET /characters/{id}/spells``: slot
    totals plus known spells in one response.
    """

    spell_slots: list[SpellSlotResponse] = []
    spells: list[CharacterSpellResponse] = []
