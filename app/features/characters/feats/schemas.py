"""Schemas for granting feats to a character."""

from pydantic import BaseModel, ConfigDict


class CharacterFeatAdd(BaseModel):
    """
    Grant a feat to a character.

    ``ability_score_increase_id`` is optional. If provided, it must
    reference one of that specific feat's own ``Feat.ability_score_increases``
    rows — validated in ``CharacterFeatService._validate_ability_score_increase``.
    Omit it entirely for feats that don't offer a choice (or to grant the
    feat without selecting an ASI).
    """

    feat_id: int
    ability_score_increase_id: int | None = None


class CharacterFeatUpdate(BaseModel):
    """
    Change (or clear) the ASI choice on an already-granted feat.

    Pass ``ability_score_increase_id`` to set/replace the choice, or
    ``None`` to clear it. There's no way to change ``feat_id`` itself —
    remove the grant and add a new one instead.
    """

    ability_score_increase_id: int | None = None


class CharacterFeatResponse(BaseModel):
    """Aggregates a character's feat grant with its chosen ASI, if any."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
    feat_id: int
    ability_score_increase_id: int | None = None
