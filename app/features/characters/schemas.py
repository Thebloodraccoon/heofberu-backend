"""Character schemas, including the aggregated CharacterResponse."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import AbilityScore, CharacterFeatSource, FeatureSourceType
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

    backstory: str = ""
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
    One-shot creation payload for a level-1 character.

    ``level`` is not accepted — every character starts at level 1 and
    grows only through the level-up endpoint. HP is fully server-derived
    and not part of the payload at all: at level 1 the maximum is fixed
    (class hit-die faces + effective CON modifier), ``current_hp`` starts
    equal to it and ``temp_hp`` at 0.

    ``extra="forbid"`` rejects unknown fields with a 422 so stale clients
    that still send removed fields (e.g. ``level``/``max_hp``) fail loudly
    instead of being silently ignored.

    ``skill_ids`` are the class skill-proficiency choices: each must exist,
    belong to the class's ``available_skills``, and the total must not
    exceed the class's ``skill_choice_count``. The background's granted
    skills (when ``background_id`` is set) are added automatically.

    ``item_choice_ids`` are the starting-equipment "pick N of M" choices
    (the ids of the ``SourceItemChoiceOption`` rows the player picked from
    the class's/background's choice groups). Each id must belong to one of
    the character's sources' choice groups, and every such group must be
    answered with exactly ``pick_count`` selected options — anything else
    is rejected with a 400 so no requested choice is ever silently
    dropped.
    """

    model_config = ConfigDict(extra="forbid")

    # Base ability scores — what the player entered, before racial or
    # feat bonuses. Effective (post-bonus) totals are exposed separately
    # on CharacterResponse via the ability_scores field.
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

    Note: ``class_id``, ``subclass_id``, ``race_id``, ``subrace_id``, and
    ``background_id`` cannot be changed via this schema — a character's
    class, subclass, race, subrace, and background are set at creation and
    only the subclass/subrace can be changed afterwards, through the
    dedicated ``PATCH /characters/{id}/progression/subclass`` and
    ``PATCH /characters/{id}/progression/subrace`` endpoints (which also
    keep the character's granted class/subclass/subrace features in sync).
    ``level`` and the base ability scores (``strength``..``charisma``) are
    likewise not editable here: level changes go through the dedicated
    level-up endpoint, and base scores only change via that endpoint's
    Ability Score Improvement choice or a GM ASI grant.
    ``max_hp`` is GM-only — see ``PATCH /characters/{id}/gm-panel/max-hp``.
    Skill proficiencies are fixed at creation (class choices + background
    grants); saving throws come from the class — neither is editable.
    ``hit_dice`` and ``speed`` are not editable either — they are derived
    from the character's class and race on every read (see
    ``CharacterStatsService``). ``armor_class`` and ``shield`` are plain
    editable columns — there is no dynamic armor calculation anymore.
    """

    name: str | None = None

    current_hp: int | None = Field(default=None, ge=0)
    temp_hp: int | None = Field(default=None, ge=0)

    armor_class: int | None = Field(default=None, ge=0)
    shield: int | None = Field(default=None, ge=0)

    backstory: str | None = None
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
    Effective (post-bonus) ability score totals — base value plus race
    and feat bonuses. Backed by the ``character_ability_scores`` cache
    table; see ``CharacterAbilityScoreCalculator`` for how it's computed
    and ``CharacterStatsService`` for the write paths that refresh it
    (character create, feat grant/update/remove, level-up ASI, GM ASI
    grant, race change). Reads never recompute the cache.
    """

    model_config = ConfigDict(from_attributes=True)

    strength_total: int
    dexterity_total: int
    constitution_total: int
    intelligence_total: int
    wisdom_total: int
    charisma_total: int


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

    The raw base ability scores are accepted on input (and read from the
    row via ``from_attributes``) but are EXCLUDED from serialized output —
    clients consume the effective totals from ``ability_scores`` instead,
    and the original base values are exposed to the GM through
    ``GET /characters/{id}/gm-panel/stats``. They carry inert defaults so
    the cached-response JSON round-trips without them.

    ``hit_dice`` and ``speed`` are not read from the character row (the
    row holds no such columns anymore) — they are derived from the class
    and race by ``CharacterStatsService`` and written onto the response in
    ``CharacterService._to_response``. They are declared here (with
    defaults) so the response stays flat, but are never accepted by
    ``CharacterCreate``/``CharacterUpdate``. ``armor_class``/``shield``
    come straight off the row — they are plain editable columns.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int

    level: int
    current_hp: int
    max_hp: int
    temp_hp: int

    # Raw base ability scores — accepted on input and read from the row,
    # but excluded from serialized output (clients use ``ability_scores``;
    # the GM sees base values via /gm-panel/stats). Inert defaults keep
    # cached-response JSON round-trips working.
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


class CharacterFeatResponse(BaseModel):
    """Aggregates a character's feat grant with its chosen ASI and feat brief."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int
    feat_id: int
    ability_score_increase_id: int | None = None
    source_type: CharacterFeatSource = CharacterFeatSource.GM
    feat: FeatBriefResponse | None = None


class CharacterFeatureBriefResponse(BaseModel):
    """
    Feature summary embedded in a character's feature grant row.

    Unlike the catalog listing row (``FeatureGetAllResponse``) this
    carries ``description`` so the sheet can render details without a
    follow-up call.
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
    full item record (``ItemResponse``) so the sheet can render details
    without a follow-up call.
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
