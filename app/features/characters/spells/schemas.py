"""Schemas for character spell slots and known spells."""

from pydantic import BaseModel, ConfigDict

from app.constants import SpellLevel
from app.features.spells.schemas import SpellResponse


class SpellSlotResponse(BaseModel):
    """A character's spell slot entry for one level."""

    model_config = ConfigDict(from_attributes=True)

    spell_level: str
    total: int
    used: int


class SpellSlotUpdate(BaseModel):
    """
    Update the used/total count for a single spell slot level.

    ``level`` is validated against the ``SpellLevel`` enum, so a request
    with anything other than a known level string (e.g. ``"LEVEL_3"`` or
    ``"CANTRIP"``) is rejected with a 422 at the schema layer — the old
    free-form ``str`` let arbitrary strings through until they hit the
    DB's check constraint.
    """

    level: SpellLevel
    used: int | None = None
    total: int | None = None


class CharacterSpellAdd(BaseModel):
    """Payload for adding a known spell to a character."""

    spell_id: int


class CharacterSpellResponse(BaseModel):
    """A known-spell entry returned on the character."""

    model_config = ConfigDict(from_attributes=True)

    spell_id: int
    spell: SpellResponse
