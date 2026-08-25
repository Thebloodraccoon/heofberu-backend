"""Request/response schemas for a feature's fixed ability-score increases."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import AbilityScore


def _validate_unique_abilities(items: list["AbilityIncreaseItem"]) -> list["AbilityIncreaseItem"]:
    abilities = [item.ability for item in items]
    if len(abilities) != len(set(abilities)):
        raise ValueError("Duplicate ability in a feature's ability increases is not allowed.")
    return items


class AbilityIncreaseItem(BaseModel):
    """
    One fixed ability-score effect of a feature: ``amount`` is added to
    the effective total while the feature is granted; ``new_cap``, when
    set, raises that ability's maximum score above the standard 20
    (e.g. Primal Champion's ``{"ability": "STR", "amount": 4, "new_cap": 24}``).
    """

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore
    amount: int
    new_cap: int | None = None


class AbilityIncreasesUpdate(BaseModel):
    """Full replacement list of a feature's ability-score increases."""

    ability_increases: list[AbilityIncreaseItem]

    @field_validator("ability_increases")
    def validate_unique_abilities(cls, value):
        return _validate_unique_abilities(value)


class FeatureAbilityIncreasesResponse(BaseModel):
    """A feature's fixed ability-score increases, as returned by the API."""

    feature_id: int
    ability_increases: list[AbilityIncreaseItem] = []
