"""Response schemas for a character's granted feats."""

from pydantic import BaseModel, ConfigDict, Field

from app.constants import CharacterFeatSource
from app.features.characters.grants.schemas import ChosenOptionResponse, GrantEffectsResponse


class FeatBriefResponse(BaseModel):
    """
    Feat name/description embedded in a character's feat grant row, plus
    ``effects_summary`` — the same human-readable effect rendering
    ``FeatureResponse``/``NestedFeatureResponse`` expose (a feat IS a
    ``Feature``).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str = ""
    effects_summary: str = ""


class CharacterFeatResponse(BaseModel):
    """
    Aggregates a character's feat grant with its feat brief, everything it
    applies to the character (``effects`` — a feat is a ``Feature`` too
    and may carry skill/save/armor/weapon/spell effects beyond its ASI), and
    the player's resolved picks (``choices``) — a picked ASI option is just
    one more entry there (``ability_effects``), same as any other feature's
    choice group; there is no dedicated ASI field.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
    feat_id: int
    source_type: CharacterFeatSource = CharacterFeatSource.GM
    feat: FeatBriefResponse | None = None
    effects: GrantEffectsResponse = Field(default_factory=GrantEffectsResponse)
    choices: list[ChosenOptionResponse] = Field(default_factory=list)
