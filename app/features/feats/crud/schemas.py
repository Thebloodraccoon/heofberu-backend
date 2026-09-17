"""Request/response schemas for the feat endpoints."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import AbilityScore
from app.features.features.crud.schemas import FeatPrerequisiteFields, FeatPrerequisiteFieldsUpdate
from app.features.features.effects.schemas import ChoiceGroupResponse, StaticEffectGroup


class FeatBase(FeatPrerequisiteFields):
    """
    Base feat fields shared by create, update, and response schemas.

    ``prerequisite_*``/``min_level`` (plus their validation) come from
    :class:`FeatPrerequisiteFields` — the same underlying ``Feature``
    columns the generic ``/features`` endpoint writes for ``source_type=FEAT``
    rows, so the field set lives in one place.
    """

    name: str
    description: str = ""


class AbilityScoreIncreaseItem(BaseModel):
    """A single ASI choice granted by a feat, e.g. {"ability": "STR", "amount": 1}."""

    ability: AbilityScore
    amount: int = 1


def _validate_unique_asi_abilities(
    ability_score_increases: list[AbilityScoreIncreaseItem],
) -> list[AbilityScoreIncreaseItem]:
    """Reject lists containing duplicate abilities."""

    abilities = [item.ability for item in ability_score_increases]

    if len(abilities) != len(set(abilities)):
        duplicates = {a for a in abilities if abilities.count(a) > 1}
        raise ValueError(f"Duplicate ability score(s): {sorted(duplicates)}")

    return ability_score_increases


class FeatCreate(FeatBase):
    """
    Create payload for a feat.

    ``ability_score_increases`` is optional with full-replace-from-empty
    semantics; it is a simple child table, not a nested dependency.
    """

    ability_score_increases: list[AbilityScoreIncreaseItem] | None = None

    @field_validator("ability_score_increases")
    def validate_unique_asi_abilities(cls, value):
        """Reject ASI lists containing duplicate abilities."""

        if value is None:
            return value

        return _validate_unique_asi_abilities(value)


class FeatUpdate(FeatPrerequisiteFieldsUpdate):
    """
    All fields optional — only provided fields are updated (PATCH semantics).

    Excludes ``ability_score_increases`` so that list keeps its own PUT
    full-replace endpoint.
    """

    name: str | None = None
    description: str | None = None


class FeatResponse(FeatBase):
    """
    Full feat representation returned by the API.

    Mirrors ``FeatureResponse`` exactly: ``choice_groups`` plus the fixed
    effects grouped by kind (``static_groups``), ``effects_summary`` as a
    plain ``Feature`` property, and ``has_static_effects``/``has_choices``
    as real denormalized columns (a feat IS a ``Feature``,
    ``source_type=FEAT``). An ASI choice (e.g.
    Resilient's "+1 to an ability score") lives in ``choice_groups`` like any
    other choice; a fixed ASI would show up under ``static_groups``. Feats
    currently have no write endpoints for effects beyond ``POST``'s embedded
    ``ability_score_increases``, so these are populated via the effect
    engine's reads only.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    choice_groups: list[ChoiceGroupResponse] = []
    static_groups: list[StaticEffectGroup] = []
    has_static_effects: bool = False
    has_choices: bool = False
    effects_summary: str = ""


class FeatGetAllResponse(BaseModel):
    """Lightweight listing row: no description, mirroring ``FeatureGetAllResponse``'s two effect flags."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    min_level: int | None = None
    has_static_effects: bool = False
    has_choices: bool = False
