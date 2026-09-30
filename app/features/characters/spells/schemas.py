"""Schemas for character spell slots and known spells."""

from pydantic import BaseModel, ConfigDict

from app.features.spells.crud.schemas import SpellBase


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


class CharacterSpellResponse(SpellBase):
    """
    A spell as shown on a character: every spell field plus its ``id``, but
    none of the catalog's ``available_*`` lists — on the sheet the spell is
    already known/granted, so who else may take it doesn't matter (the full
    record stays at ``GET /spells/{id}``).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int


class CharacterSpellsResponse(BaseModel):
    """
    Combined read model behind ``GET /characters/{id}/spells``, every spell
    list a plain list of spells:

    - ``spells`` — the free-form known spells (count against slot totals);
    - ``gm_spells`` — spells the GM granted directly (removable via
      ``DELETE /gm-panel/spells?spell_id=``);
    - ``feature_spells`` — spells the character's feature/feat grants give
      (computed, deduplicated; they go away only with their grant).
    """

    spell_slots: list[SpellSlotResponse] = []
    spells: list[CharacterSpellResponse] = []
    gm_spells: list[CharacterSpellResponse] = []
    feature_spells: list[CharacterSpellResponse] = []
