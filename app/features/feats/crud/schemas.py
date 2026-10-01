"""Request/response schemas for the feat endpoints."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.constants import AbilityScore
from app.features.features.crud.schemas import FeatPrerequisiteFields, FeatPrerequisiteFieldsUpdate
from app.features.features.effects.schemas import ChoiceGroupResponse, StaticEffectGroup

# Input bounds follow the column sizes; responses stay unconstrained so legacy rows always serialize.
FeatName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
PrerequisiteScore = Annotated[int, Field(ge=1, le=30)]
AbilityScoreAmount = Annotated[int, Field(ge=1, le=10)]


def _reject_explicit_null(value):
    """Omit a field to leave it unchanged; ``null`` is not a valid value for a NOT NULL column."""

    if value is None:
        raise ValueError("This field cannot be null; omit it to leave it unchanged.")

    return value


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
    amount: AbilityScoreAmount = 1


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

    name: FeatName
    prerequisite_minimum_score: PrerequisiteScore | None = None
    ability_score_increases: list[AbilityScoreIncreaseItem] | None = Field(default=None, max_length=6)

    @model_validator(mode="after")
    def validate_prerequisite_pair(self):
        """The ability prerequisite needs both the ability and its minimum score (or neither)."""

        if (self.prerequisite_ability is None) != (self.prerequisite_minimum_score is None):
            raise ValueError("prerequisite_ability and prerequisite_minimum_score must be set together.")

        return self

    @field_validator("ability_score_increases")
    def validate_unique_asi_abilities(cls, value):
        """Reject ASI lists containing duplicate abilities."""

        if value is None:
            return value

        return _validate_unique_asi_abilities(value)


class FeatUpdate(FeatPrerequisiteFieldsUpdate):
    """
    All fields optional — only provided fields are updated (PATCH semantics).

    Excludes ``ability_score_increases``: ASI options are managed through the
    feat's effects/choice-group endpoints. An explicit ``null`` is rejected for
    the NOT NULL columns (``name``, ``description``, ``prerequisite_description``).
    """

    name: FeatName | None = None
    description: str | None = None
    prerequisite_minimum_score: PrerequisiteScore | None = None

    @field_validator("name", "description", "prerequisite_description")
    @classmethod
    def reject_explicit_null(cls, value):
        """Reject an explicit ``null`` for the NOT NULL columns."""

        return _reject_explicit_null(value)


class FeatResponse(FeatBase):
    """
    Full feat representation returned by the API.

    Mirrors ``FeatureResponse`` exactly: ``choice_groups`` plus the fixed
    effects grouped by kind (``static_groups``), ``effects_summary`` as a
    plain ``Feature`` property, and ``has_static_effects``/``has_choices``
    as real denormalized columns (a feat IS a ``Feature``,
    ``source_type=FEAT``). An ASI choice (e.g. Resilient's "+1 to an ability
    score") lives in ``choice_groups`` like any other choice; a fixed ASI
    would show up under ``static_groups``. Effects are written through
    ``POST``'s embedded ``ability_score_increases`` or ``/feats/{id}/effects``
    and ``/feats/{id}/choice-groups``.
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
