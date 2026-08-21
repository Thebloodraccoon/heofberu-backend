"""Schemas for character spell slots and known spells."""

from pydantic import BaseModel, ConfigDict

from app.features.spells.crud.schemas import SpellResponse


class SpellSlotResponse(BaseModel):
    """
    A character's spell slot entry for one level.

    Only ``total`` is exposed: it always comes from the character's
    class/level spell-slot progression (applied on create and re-applied
    on level-up/class change) and doubles as the cap on how many spells
    of that level the character may know. There is no per-slot ``used``
    tracking — slots are not spent, they are capacity for known spells.
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
    Combined read model behind ``GET /characters/{id}/spells``: the
    class-derived slot totals per level together with the known spells,
    so a client renders the whole spellcasting picture from one call.
    """

    spell_slots: list[SpellSlotResponse] = []
    spells: list[CharacterSpellResponse] = []
