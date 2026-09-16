"""Request schemas for GM feat grants on a character."""

from pydantic import BaseModel, Field

from app.features.characters.grants.schemas import ChoiceAnswerItem


class CharacterFeatAdd(BaseModel):
    """
    Grant a feat. ``ability_score_increase_id`` picks the feat's ASI choice
    up front if given, but — like any other choice group answered via
    ``choices`` (e.g. Skilled's 3 skill picks) — it may be left unset: an
    unanswered choice group stays pending on the grant rather than blocking
    the grant, to be picked up later via ``PATCH /features/{id}/choices`` or
    ``GET /grants/pending``.
    """

    feat_id: int
    ability_score_increase_id: int | None = None
    choices: list[ChoiceAnswerItem] = Field(default_factory=list)


class CharacterFeatUpdate(BaseModel):
    """Change the ASI choice on an already-granted feat; a feat offering ASI options always keeps one."""

    ability_score_increase_id: int | None = None
