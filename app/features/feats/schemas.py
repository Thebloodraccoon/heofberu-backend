"""Request/response schemas for the feat endpoints."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import AbilityScore


class FeatBase(BaseModel):
    """Base feat fields shared by create, update, and response schemas."""

    name: str
    description: str = ""

    prerequisite_ability: AbilityScore | None = None
    prerequisite_minimum_score: int | None = None
    prerequisite_description: str = ""

    is_homebrew: bool = False


class AbilityScoreIncreaseItem(BaseModel):
    """A single ASI choice granted by a feat, e.g. {"ability": "STR", "amount": 1}."""

    ability: AbilityScore
    amount: int = 1


def _validate_unique_asi_abilities(
    ability_score_increases: list[AbilityScoreIncreaseItem],
) -> list[AbilityScoreIncreaseItem]:
    abilities = [item.ability for item in ability_score_increases]
    if len(abilities) != len(set(abilities)):
        duplicates = {a for a in abilities if abilities.count(a) > 1}
        raise ValueError(f"Duplicate ability score(s): {sorted(duplicates)}")
    return ability_score_increases


class FeatCreate(FeatBase):
    """
    Create payload for a feat.

    ``ability_score_increases`` is optional — a feat can be created
    without any ASI of its own (e.g. Alert) or with a set of choices
    supplied up front (e.g. Resilient offers "choose one ability"), same
    "full replace from empty" semantics as ``RaceCreate.ability_bonuses``.
    """

    ability_score_increases: list[AbilityScoreIncreaseItem] | None = None

    @field_validator("ability_score_increases")
    def validate_unique_asi_abilities(cls, value):
        """Reject ASI lists containing duplicate abilities."""
        if value is None:
            return value
        return _validate_unique_asi_abilities(value)


class FeatUpdate(BaseModel):
    """
    All fields optional — only provided fields are updated (PATCH semantics).

    Deliberately does NOT include ability_score_increases: that keeps its
    own PUT endpoint with explicit full-replace semantics, same reasoning
    as ``RaceUpdate`` and ability_bonuses.
    """

    name: str | None = None
    description: str | None = None
    prerequisite_ability: AbilityScore | None = None
    prerequisite_minimum_score: int | None = None
    prerequisite_description: str | None = None
    is_homebrew: bool | None = None


class AbilityScoreIncreasesUpdate(BaseModel):
    """Full replacement list of ASI choices for a feat."""

    ability_score_increases: list[AbilityScoreIncreaseItem]

    @field_validator("ability_score_increases")
    def validate_unique_asi_abilities(cls, ability_score_increases):
        """Reject ASI lists containing duplicate abilities."""
        return _validate_unique_asi_abilities(ability_score_increases)


class AbilityScoreIncreaseResponse(BaseModel):
    """A feat's ASI choice as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ability: AbilityScore
    amount: int


class FeatResponse(FeatBase):
    """Full feat representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by_id: int | None = None
    ability_score_increases: list[AbilityScoreIncreaseResponse] = []


class FeatBriefResponse(BaseModel):
    """Lightweight listing row: no description, no ASI choices."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_homebrew: bool
