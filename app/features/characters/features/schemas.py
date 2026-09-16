"""Response schemas for a character's granted (non-feat) features."""

from pydantic import BaseModel, ConfigDict

from app.constants import FeatureSourceType, GrantSource
from app.features.characters.grants.schemas import ChosenOptionResponse, GrantEffectsResponse


class CharacterFeatureBriefResponse(BaseModel):
    """
    Feature summary embedded in a character's feature grant row, carrying
    ``description`` and ``effects_summary`` (the same human-readable effect
    rendering ``FeatureResponse``/``NestedFeatureResponse`` expose) so the
    sheet renders details without a follow-up call to ``/features/{id}``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_type: FeatureSourceType
    level: int | None = None
    description: str = ""
    effects_summary: str = ""


class CharacterFeatureResponse(BaseModel):
    """
    Aggregates a character's feature grant with a brief feature summary,
    everything it materialized on the character (``effects``), and the
    player's resolved picks for its choice groups (``choices``).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
    feature_id: int
    grant_source: GrantSource = GrantSource.AUTO
    feature: CharacterFeatureBriefResponse
    effects: GrantEffectsResponse = GrantEffectsResponse()
    choices: list[ChosenOptionResponse] = []
