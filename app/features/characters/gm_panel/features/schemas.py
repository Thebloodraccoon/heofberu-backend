"""Request schemas for GM feature grants on a character.

The response shape (``CharacterFeatureResponse`` and its embedded brief)
lives in the top-level ``characters/schemas.py`` because it is shared
by the player-facing reads in ``crud/`` and by these writes.
"""

from pydantic import BaseModel


class CharacterFeatureAdd(BaseModel):
    """Record a reference feature on a character."""

    feature_id: int
    notes: str = ""


class CharacterFeatureUpdate(BaseModel):
    """Replace the notes on an already-recorded feature."""

    notes: str | None = None
