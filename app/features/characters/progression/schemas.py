"""Schemas for character progression: subclass/subrace/background setup, leveling up, rebuild."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import ASI_LEVELS, AbilityScore, ASILevelChoice
from app.core.types import EntityId
from app.features.characters.schemas import ABILITY_SCORE_MAX, ABILITY_SCORE_MIN

# A single ASI at a level grants up to +2 total across the six abilities
# (e.g. +2 to one ability, or +1/+1 to two). Individual increments are
# bounded 1..2 and the total is validated to stay within that budget.
ASI_TOTAL_BUDGET = 2

# Bounds on client-supplied lists and numbers (the real limits are enforced by the service).
MAX_FEATURE_CHOICES = 50
MAX_REBUILD_SKILLS = 30
MAX_HIT_POINTS_GAINED = 50
MAX_REBUILD_HP = 1000


class SubclassChange(BaseModel):
    """
    Set or clear a character's subclass.

    ``subclass_id`` must reference a subclass of the character's current
    class (validated by the service); ``subclass_id: null`` clears it.
    Setting a subclass grants its features at or below the character's
    current level.
    """

    subclass_id: EntityId | None = None


class SubraceChange(BaseModel):
    """
    Set or clear a character's subrace.

    ``subrace_id`` must reference a subrace of the character's current
    race (validated by the service; a character without a race cannot
    hold a subrace); ``subrace_id: null`` clears it. Setting a subrace
    grants its features at or below the character's current level.
    """

    subrace_id: EntityId | None = None


class BackgroundChange(BaseModel):
    """
    Set a character's background — only allowed while the character has
    none (a background picked at creation can never be swapped).

    Grants everything a background grants at creation: its features (via
    progression sync), its granted skills (BACKGROUND-sourced proficiency
    rows, kept alongside rows from other sources) and its starting
    equipment (merged into existing stacks).
    """

    background_id: EntityId


class ASIIncreaseItem(BaseModel):
    """One increment of an Ability Score Improvement, e.g. {"ability": "STR", "amount": 2}."""

    ability: AbilityScore
    amount: int = Field(default=1, ge=1, le=ASI_TOTAL_BUDGET)


def _validate_asi_increases(increases: list[ASIIncreaseItem]) -> list[ASIIncreaseItem]:
    """Reject duplicate abilities and totals outside the +1..+2 ASI budget."""

    abilities = [item.ability for item in increases]
    if len(abilities) != len(set(abilities)):
        raise ValueError("Duplicate ability in an ASI choice is not allowed.")

    total = sum(item.amount for item in increases)
    if not (1 <= total <= ASI_TOTAL_BUDGET):
        raise ValueError(f"An ASI choice must grant between 1 and {ASI_TOTAL_BUDGET} total points.")

    return increases


class ASIChoice(BaseModel):
    """Level-up choice taking the Ability Score Improvement option."""

    type: Literal["ASI"] = "ASI"
    increases: list[ASIIncreaseItem] = Field(max_length=len(AbilityScore))

    @field_validator("increases")
    def validate_increases(cls, increases):
        """Validate the ASI increments against the +1..+2 budget."""

        return _validate_asi_increases(increases)


class FeatChoice(BaseModel):
    """
    Level-up choice taking a feat instead of the Ability Score Improvement.

    ``ability_score_increase_id`` is the id of the specific ASI option (a
    ``feature_ability_score_effects`` row) of a feat that offers ASI options
    of its own (e.g. Resilient). A rebuild rejects such a feat without one
    (422); a level-up rejects it through the unresolved choice group (422).
    The feat's ``min_level`` and the ability cap of 20 apply to the pick.
    """

    type: Literal["FEAT"] = "FEAT"
    feat_id: EntityId
    ability_score_increase_id: EntityId | None = None


LevelUpChoice = Annotated[ASIChoice | FeatChoice, Field(discriminator="type")]


class RebuildASIChoice(BaseModel):
    """
    One resolved Ability Score Improvement choice supplied with a
    rebuild, for an ASI level (see ``ASI_LEVELS``) the character has
    already reached. A rebuild must supply exactly one of these per
    reached ASI level — see ``CharacterRebuildRequest``.
    """

    class_level: int
    choice: LevelUpChoice

    @field_validator("class_level")
    def validate_class_level(cls, class_level):
        """Reject a class_level that isn't one of the ASI levels."""

        if class_level not in ASI_LEVELS:
            raise ValueError(f"class_level must be one of {sorted(ASI_LEVELS)}.")

        return class_level


class CharacterRebuildRequest(BaseModel):
    """
    Full point-rebuild payload: the same "build" fields taken at character
    creation (class/subclass/race/subrace/background, base ability
    scores, class skill choices) applied to an existing character, plus
    the two values a rebuild cannot derive on its own:

    - ``max_hp``: the player's rolled (or averaged) HP total for the new
      build. The service validates it falls within the range the new
      class's hit die and current level allow (level 1's die + CON is
      fixed; each level above it contributes between 1 and die + CON) —
      see ``progression.rules.max_hp_bounds``.
    - ``asi_choices``: one entry for every ASI level (see ``ASI_LEVELS``)
      the character has already reached, replacing its prior ASI/feat
      choices at those levels — the new build's ability scores/class can
      make the old ones invalid (e.g. no longer a legal ability-cap
      increase, or a feat prerequisite no longer met), so they are never
      carried over automatically.

    Everything else derived from these choices is recomputed by the
    service — skill proficiencies, source-owned features, spell slots,
    and the ability-score cache — and known spells are cleared.
    ``level``, notes, personality, backstory, inventory, and GM-granted
    feats are untouched (see
    ``CharacterProgressionService.rebuild_character``). ``extra="forbid"``
    rejects stale/unknown fields.
    """

    model_config = ConfigDict(extra="forbid")

    class_id: EntityId
    subclass_id: EntityId | None = None

    race_id: EntityId
    subrace_id: EntityId | None = None

    background_id: EntityId | None = None

    strength: int = Field(ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    dexterity: int = Field(ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    constitution: int = Field(ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    intelligence: int = Field(ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    wisdom: int = Field(ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    charisma: int = Field(ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)

    max_hp: int = Field(ge=1, le=MAX_REBUILD_HP)

    skill_ids: list[EntityId] = Field(default_factory=list, max_length=MAX_REBUILD_SKILLS)
    asi_choices: list[RebuildASIChoice] = Field(default_factory=list, max_length=len(ASI_LEVELS))

    @field_validator("skill_ids")
    def validate_unique_skill_ids(cls, skill_ids):
        """Reject lists containing duplicate skill IDs."""

        if len(skill_ids) != len(set(skill_ids)):
            raise ValueError("Duplicate skill IDs are not allowed.")

        return skill_ids

    @field_validator("asi_choices")
    def validate_unique_asi_levels(cls, asi_choices):
        """Reject more than one supplied choice for the same ASI level."""

        levels = [item.class_level for item in asi_choices]
        if len(levels) != len(set(levels)):
            raise ValueError("Duplicate class_level in asi_choices is not allowed.")

        return asi_choices


class LevelUpFeatureChoiceAnswer(BaseModel):
    """
    One picked option, for one choice group, on one feature newly unlocked
    by this level-up (e.g. a class feature at level 3 that grants "choose a
    tool proficiency"). ``feature_id`` identifies the catalog feature — not
    the per-character grant, whose id doesn't exist until the level-up
    creates it — since ``choice_group_id``/``choice_option_id`` are reference
    data, fetchable ahead of time from ``GET /classes/{id}/features`` (or the
    equivalent for the granting source) before submitting the level-up.

    No ``skill_id``/``spell_id`` field: picking an option that carries an
    open ("any skill"/"any spell") effect isn't supported yet — the whole
    level-up is rejected (422) if one is picked.
    """

    feature_id: EntityId
    choice_group_id: EntityId
    choice_option_id: EntityId


class LevelUpRequest(BaseModel):
    """
    Level a character up exactly one level.

    ``hit_points_gained`` is optional: when omitted, the standard average
    (half the class hit die + 1 + CON modifier) is used; when provided it
    must be within ``[1, hit die + CON modifier]``.

    ``choice`` is required when the new level is an Ability Score
    Improvement level and rejected otherwise. See ``ASI_LEVELS``.

    ``feature_choices`` resolves the "pick N of M" choice group(s) of any
    OTHER feature this level unlocks (a class feature granting a skill/tool/
    armor/weapon proficiency or a bonus spell, a subclass trait, ...) —
    unrelated to the ASI-vs-feat ``choice`` above. A newly unlocked feature
    with a still-unanswered group after applying these aborts the whole
    level-up with ``GrantChoiceRequiredException`` (422) naming what's
    missing, exactly like a missing ASI ``choice`` does — the grant is never
    left silently half-resolved. A feature with no choice groups needs no
    entry here; its fixed effects apply automatically.
    """

    hit_points_gained: int | None = Field(default=None, ge=1, le=MAX_HIT_POINTS_GAINED)
    choice: LevelUpChoice | None = None
    feature_choices: list[LevelUpFeatureChoiceAnswer] = Field(default_factory=list, max_length=MAX_FEATURE_CHOICES)


class CanLevelUpResponse(BaseModel):
    """
    Whether the character may take another level-up.

    ``max_level`` is the GM-set cap from ``character_max_levels``;
    leveling up is possible while ``current_level < max_level``.
    """

    can_level_up: bool
    current_level: int
    max_level: int


class ASIIncreaseResponse(BaseModel):
    """A single increment of a recorded ASI choice."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore
    amount: int


class CharacterASIChoiceResponse(BaseModel):
    """
    A recorded ASI-level resolution for a character. ``increases``
    serializes the typed ``CharacterASIChoiceIncrease`` child rows
    (empty for FEAT-type choices, whose stat effect flows through the
    granted feat).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
    class_level: int | None = None
    choice_type: ASILevelChoice
    feat_id: int | None = None
    ability_score_increase_id: int | None = None
    increases: list[ASIIncreaseResponse] = Field(default_factory=list)
