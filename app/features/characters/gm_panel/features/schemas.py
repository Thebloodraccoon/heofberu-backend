"""Request schemas for GM feature grants on a character."""

from pydantic import BaseModel


class CharacterFeatureAdd(BaseModel):
    """Record a reference feature on a character."""

    feature_id: int
    notes: str = ""


class CharacterFeatureUpdate(BaseModel):
    """Replace the notes on an already-recorded feature."""

    notes: str | None = None
