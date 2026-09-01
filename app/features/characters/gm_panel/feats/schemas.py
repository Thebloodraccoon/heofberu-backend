"""Request schemas for GM feat grants on a character."""

from pydantic import BaseModel


class CharacterFeatAdd(BaseModel):
    """Grant a feat; ``ability_score_increase_id`` is required for feats offering ASI options."""

    feat_id: int
    ability_score_increase_id: int | None = None


class CharacterFeatUpdate(BaseModel):
    """Change the ASI choice on an already-granted feat; a feat offering ASI options always keeps one."""

    ability_score_increase_id: int | None = None
