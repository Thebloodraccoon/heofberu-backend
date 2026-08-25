"""
Request schemas for GM feat grants on a character.

The response shape (``CharacterFeatResponse`` and its embedded brief)
lives in the top-level ``characters/schemas.py`` because it is shared
by the player-facing reads in ``crud/`` and by these writes.
"""

from pydantic import BaseModel


class CharacterFeatAdd(BaseModel):
    """
    Grant a feat to a character. ``ability_score_increase_id`` is
    optional for feats without ASI options and REQUIRED for feats that
    offer them (the service rejects the grant otherwise).
    """

    feat_id: int
    ability_score_increase_id: int | None = None


class CharacterFeatUpdate(BaseModel):
    """
    Change the ASI choice on an already-granted feat; a feat offering
    ASI options must always keep one (clearing is rejected by the
    service).
    """

    ability_score_increase_id: int | None = None
