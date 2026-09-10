"""Request schemas for GM feature grants on a character."""

from pydantic import BaseModel, Field

from app.features.characters.grants.schemas import ChoiceAnswerItem


class CharacterFeatureAdd(BaseModel):
    """
    Record a reference feature on a character. ``choices`` answers the
    feature's choice groups, if it has any; a group left unanswered stays
    pending on the grant rather than blocking it — pick it up later via
    ``PATCH /features/{id}/choices`` or ``GET /grants/pending``.
    """

    feature_id: int
    notes: str = ""
    choices: list[ChoiceAnswerItem] = Field(default_factory=list)


class CharacterFeatureUpdate(BaseModel):
    """Replace the notes on an already-recorded feature."""

    notes: str | None = None
