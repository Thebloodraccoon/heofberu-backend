"""Character schemas, including the aggregated CharacterResponse."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import (
    AbilityScore,
    CharacterFeatSource,
    FeatureSourceType,
)
from app.features.characters.conditions.schemas import CharacterConditionResponse
from app.features.items.crud.schemas import ItemResponse

# Standard D&D 5e ability-score range for values entered directly by a
# player (before racial/feat bonuses are applied) — matches the typical
# point-buy/standard-array range. Bonuses on top of this (race, feats)
# are computed separately and are not bound by this range themselves.
ABILITY_SCORE_MIN = 3
ABILITY_SCORE_MAX = 18


class CharacterBase(BaseModel):
    """Base character fields shared by create and response schemas."""

    name: str

    class_id: int
    subclass_id: int | None = None

    race_id: int | None = None
    subrace_id: int | None = None

    background_id: int | None = None

    # Combat stats entered/set directly on the sheet — there is no
    # dynamic armor calculation anymore; whatever is stored here is what
    # every read returns.
    armor_class: int = Field(default=10, ge=0)
    shield: int = Field(default=0, ge=0)

    # Base ability scores — what the player entered, before racial or
    # feat bonuses. Effective (post-bonus) totals are exposed separately
    # on CharacterResponse via the ability_scores field.
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int

    notes: str = ""

    # Personality card free-text fields (5e "Personality" section).
    personality_traits: str = ""
    ideals: str = ""
    bonds: str = ""
    flaws: str = ""

    money_gold: int = Field(default=0, ge=0)
    money_silver: int = Field(default=0, ge=0)
    money_copper: int = Field(default=0, ge=0)


class CharacterCreate(CharacterBase):
    """
    One-shot creation payload for a level-1 character. ``level`` and HP
    are server-derived; ``extra="forbid"`` rejects unknown/stale fields.
    """

    model_config = ConfigDict(extra="forbid")

    strength: int = Field(default=10, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    dexterity: int = Field(default=10, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    constitution: int = Field(default=10, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    intelligence: int = Field(default=10, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    wisdom: int = Field(default=10, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    charisma: int = Field(default=10, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)

    skill_ids: list[int] = Field(default_factory=list)
    item_choice_ids: list[int] = Field(default_factory=list)

    @field_validator("skill_ids")
    def validate_unique_skill_ids(cls, skill_ids):
        """Reject lists containing duplicate skill IDs."""

        if len(skill_ids) != len(set(skill_ids)):
            raise ValueError("Duplicate skill IDs are not allowed.")

        return skill_ids

    @field_validator("item_choice_ids")
    def validate_unique_item_choice_ids(cls, item_choice_ids):
        """Reject lists containing duplicate item-choice option IDs."""

        if len(item_choice_ids) != len(set(item_choice_ids)):
            raise ValueError("Duplicate item choice IDs are not allowed.")

        return item_choice_ids


class CharacterUpdate(BaseModel):
    """
    All fields optional — only provided fields are updated (PATCH semantics).
    Class/race/background, level, and base ability scores are not editable here.
    """

    name: str | None = None

    current_hp: int | None = Field(default=None, ge=0)
    temp_hp: int | None = Field(default=None, ge=0)

    armor_class: int | None = Field(default=None, ge=0)
    shield: int | None = Field(default=None, ge=0)

    # 5e inspiration — a boolean the GM grants (advantage on a roll).
    inspiration: bool | None = None

    notes: str | None = None

    personality_traits: str | None = None
    ideals: str | None = None
    bonds: str | None = None
    flaws: str | None = None

    money_gold: int | None = Field(default=None, ge=0)
    money_silver: int | None = Field(default=None, ge=0)
    money_copper: int | None = Field(default=None, ge=0)


class AbilityScoresResponse(BaseModel):
    """
    Effective (post-bonus) ability score totals, backed by the
    ``character_ability_scores`` cache — reads never recompute it.
    """

    model_config = ConfigDict(from_attributes=True)

    strength_total: int
    dexterity_total: int
    constitution_total: int
    intelligence_total: int
    wisdom_total: int
    charisma_total: int


class StatSourceContribution(BaseModel):
    """
    One source's contribution to an ability's effective total, shown as
    a human-readable "what is calculated from what" row.
    """

    source: str
    label: str
    amount: int


class AbilityStatsView(BaseModel):
    """One ability's score view: the ORIGINAL base value next to its COMPUTED total and source contributions."""

    model_config = ConfigDict(from_attributes=True)

    base: int
    total: int
    contributions: list[StatSourceContribution] = Field(default_factory=list)


class CharacterStatsResponse(BaseModel):
    """
    Player-facing view of the six abilities: ORIGINAL base values next
    to COMPUTED totals, freshly calculated (never the stale cache row).
    """

    strength: AbilityStatsView
    dexterity: AbilityStatsView
    constitution: AbilityStatsView
    intelligence: AbilityStatsView
    wisdom: AbilityStatsView
    charisma: AbilityStatsView


class SkillProficiencyResponse(BaseModel):
    """A skill proficiency row returned on the character."""

    model_config = ConfigDict(from_attributes=True)

    skill_id: int
    is_expertise: bool


class SavingThrowProficiencyResponse(BaseModel):
    """A saving throw proficiency — derived from the character's class."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore


class CharacterResponse(CharacterBase):
    """
    Aggregates response schemas from every sub-domain into one payload.
    Base ability scores are excluded from output; ``hit_dice``/``speed``
    are derived from class/race on every read.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int

    level: int
    current_hp: int
    max_hp: int
    temp_hp: int
    inspiration: bool = False

    # Raw base ability scores — accepted on input and read from the row,
    # but excluded from serialized output (clients use ``ability_scores``;
    # the base values are visible via /characters/{id}/stats). Inert
    # defaults keep cached-response JSON round-trips working.
    strength: int = Field(default=10, exclude=True)
    dexterity: int = Field(default=10, exclude=True)
    constitution: int = Field(default=10, exclude=True)
    intelligence: int = Field(default=10, exclude=True)
    wisdom: int = Field(default=10, exclude=True)
    charisma: int = Field(default=10, exclude=True)

    # Derived combat stats — populated by ``CharacterService._to_response``.
    hit_dice: str = ""
    speed: int = 30

    ability_scores: AbilityScoresResponse | None = None
    skill_proficiencies: list[SkillProficiencyResponse] = []
    saving_throw_proficiencies: list[SavingThrowProficiencyResponse] = []
    conditions: list[CharacterConditionResponse] = []


class FeatBriefResponse(BaseModel):
    """Feat name/description embedded in a character's feat grant row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str = ""


class FeatAbilityScoreIncreaseResponse(BaseModel):
    """
    The ability score a granted feat improved (its chosen ASI option),
    backed by the ``FeatAbilityScoreIncrease`` row.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    ability: AbilityScore
    amount: int = 1


class CharacterFeatResponse(BaseModel):
    """Aggregates a character's feat grant with its chosen ASI and feat brief."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
    feat_id: int
    ability_score_increase_id: int | None = None
    source_type: CharacterFeatSource = CharacterFeatSource.GM
    feat: FeatBriefResponse | None = None
    ability_score_increase: FeatAbilityScoreIncreaseResponse | None = None


class CharacterFeatureBriefResponse(BaseModel):
    """
    Feature summary embedded in a character's feature grant row, carrying
    ``description`` so the sheet renders details without a follow-up call.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_type: FeatureSourceType
    level: int | None = None
    description: str = ""


class CharacterFeatureResponse(BaseModel):
    """Aggregates a character's feature grant with notes and a brief feature summary."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
    feature_id: int
    notes: str = ""
    feature: CharacterFeatureBriefResponse


class CharacterItemResponse(BaseModel):
    """
    Aggregates an owned item stack with its quantity/state flags and the
    full item record so the sheet renders without a follow-up call.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
    item_id: int
    quantity: int
    is_equipped: bool
    is_attuned: bool
    notes: str = ""
    item: ItemResponse
