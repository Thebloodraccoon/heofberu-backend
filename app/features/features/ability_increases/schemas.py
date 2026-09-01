"""Request/response schemas for a feature's fixed ability-score increases."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import ABILITY_SCORE_CAP, MAX_ABILITY_SCORE_CAP, AbilityScore

def _validate_unique_abilities(items: list["AbilityIncreaseItem"]) -> list["AbilityIncreaseItem"]:
    """Reject lists containing duplicate abilities."""

    abilities = [item.ability for item in items]
    if len(abilities) != len(set(abilities)):
        raise ValueError("Duplicate ability in a feature's ability increases is not allowed.")
    return items

class AbilityIncreaseItem(BaseModel):
    """
    One fixed ability-score effect of a feature.

    ``amount`` is added to the effective total while the feature is granted;
    ``new_cap``, when set, raises that ability's maximum above 20 up to 30.
    """

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore
    amount: int
    new_cap: int | None = None

    @field_validator("new_cap")
    @classmethod
    def validate_new_cap(cls, value):
        """Reject ``new_cap`` values outside the allowed range."""

        if value is not None and not (ABILITY_SCORE_CAP <= value <= MAX_ABILITY_SCORE_CAP):
            raise ValueError(
                f"'new_cap' must be between {ABILITY_SCORE_CAP} and {MAX_ABILITY_SCORE_CAP}."
            )
        return value

class AbilityIncreasesUpdate(BaseModel):
    """Full replacement list of a feature's ability-score increases."""

    ability_increases: list[AbilityIncreaseItem]

    @field_validator("ability_increases")
    def validate_unique_abilities(cls, value):
        """Reject lists containing duplicate abilities."""

        return _validate_unique_abilities(value)

class FeatureAbilityIncreasesResponse(BaseModel):
    """A feature's fixed ability-score increases, as returned by the API."""

    feature_id: int
    ability_increases: list[AbilityIncreaseItem] = []
