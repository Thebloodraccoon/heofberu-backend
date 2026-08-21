"""Request schemas for GM feat grants on a character.

The response shape (``CharacterFeatResponse`` and its embedded brief)
lives in the top-level ``characters/schemas.py`` because it is shared
by the player-facing reads in ``crud/`` and by these writes.
"""

from pydantic import BaseModel


class CharacterFeatAdd(BaseModel):
    """Grant a feat to a character. ability_score_increase_id is optional."""

    feat_id: int
    ability_score_increase_id: int | None = None


class CharacterFeatUpdate(BaseModel):
    """Change (or clear) the ASI choice on an already-granted feat."""

    ability_score_increase_id: int | None = None
