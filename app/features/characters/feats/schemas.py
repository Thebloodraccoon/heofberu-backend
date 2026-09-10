"""Response schemas for a character's granted feats."""

from pydantic import BaseModel, ConfigDict

from app.constants import AbilityScore, CharacterFeatSource
from app.features.characters.grants.schemas import ChosenOptionResponse, GrantEffectsResponse


class FeatBriefResponse(BaseModel):
    """Feat name/description embedded in a character's feat grant row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str = ""


class FeatAbilityScoreIncreaseResponse(BaseModel):
    """
    The ability score a granted feat improved (its chosen ASI option),
    backed by a ``feature_ability_score_effects`` row.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    ability: AbilityScore
    amount: int = 1


class CharacterFeatResponse(BaseModel):
    """
    Aggregates a character's feat grant with its chosen ASI and feat brief,
    everything it materialized on the character (``effects`` — a feat is a
    ``Feature`` too and may carry skill/save/armor/weapon/spell effects
    beyond its ASI), and the player's resolved picks (``choices``).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
    feat_id: int
    ability_score_increase_id: int | None = None
    source_type: CharacterFeatSource = CharacterFeatSource.GM
    feat: FeatBriefResponse | None = None
    ability_score_increase: FeatAbilityScoreIncreaseResponse | None = None
    effects: GrantEffectsResponse = GrantEffectsResponse()
    choices: list[ChosenOptionResponse] = []
