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
    Update the ``used`` count for a single spell slot level.

    ``total`` is deliberately NOT settable here — it is always derived
    from the character's class/level spell-slot progression (applied on
    create and re-applied on level-up/class-change, see
    ``CharacterService._apply_spell_slot_progression``). Allowing a
    client to overwrite ``total`` would let a player grant themselves
    slots, so the field is excluded (``extra="forbid"`` rejects it with
    a 422).

    ``level`` is validated against the ``SpellLevel`` enum, so a request
    with anything other than a known level string (e.g. ``"LEVEL_3"`` or
    ``"CANTRIP"``) is rejected with a 422 at the schema layer — the old
    free-form ``str`` let arbitrary strings through until they hit the
    DB's check constraint.
    """

    model_config = ConfigDict(extra="forbid")

    level: SpellLevel
    used: int | None = None


class CharacterSpellAdd(BaseModel):
    """Payload for adding a known spell to a character."""

    spell_id: int


class CharacterSpellResponse(BaseModel):
    """A known-spell entry returned on the character."""

    model_config = ConfigDict(from_attributes=True)

    spell_id: int
    spell: SpellResponse
