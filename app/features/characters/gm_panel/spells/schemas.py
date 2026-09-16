"""Request schema for a GM directly granting a spell to a character."""

from pydantic import BaseModel


class CharacterGrantedSpellAdd(BaseModel):
    """
    Grant any spell to a character directly — no feature/feat behind it,
    no class/race eligibility check (a GM override, like a homebrew boon).
    """

    spell_id: int
