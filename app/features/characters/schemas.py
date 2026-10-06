"""Character schemas, including the aggregated CharacterResponse."""

from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

# Range of a base ability score entered directly by a player (before
# racial/feat bonuses): the typical point-buy/standard-array range.
ABILITY_SCORE_MIN = 3
ABILITY_SCORE_MAX = 18

# Input bounds: ``characters.name`` is VARCHAR(200), the money/stat columns are
# int32, and free text is capped because it is part of the cached response.
NAME_MAX_LENGTH = 200
NOTES_MAX_LENGTH = 20_000
PERSONALITY_MAX_LENGTH = 5_000
MONEY_MAX = 2_000_000_000
COMBAT_STAT_MAX = 1_000
HP_LIMIT = 100_000
INSPIRATION_MAX = 13

CharacterName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX_LENGTH)]
Notes = Annotated[str, Field(max_length=NOTES_MAX_LENGTH)]
PersonalityText = Annotated[str, Field(max_length=PERSONALITY_MAX_LENGTH)]
Money = Annotated[int, Field(ge=0, le=MONEY_MAX)]
CombatStat = Annotated[int, Field(ge=0, le=COMBAT_STAT_MAX)]


class PatchModel(BaseModel):
    """
    Base for PATCH payloads: an explicit ``null`` is a 422 for every field not
    listed in ``nullable_fields`` (omit the field to leave it unchanged).
    Without this a ``null`` for a NOT NULL column would reach the database.
    """

    nullable_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="before")
    @classmethod
    def _reject_explicit_null(cls, data: Any) -> Any:
        """Reject ``null`` for fields that cannot be null."""

        if isinstance(data, dict):
            offending = sorted(
                name
                for name, value in data.items()
                if value is None and name in cls.model_fields and name not in cls.nullable_fields
            )
            if offending:
                raise ValueError(f"null is not allowed for: {', '.join(offending)}")

        return data


class CharacterBase(BaseModel):
    """Base character fields shared by create and response schemas."""

    name: str

    class_id: int
    subclass_id: int | None = None
    race_id: int | None = None
    subrace_id: int | None = None
    background_id: int | None = None

    armor_class: int = 10
    shield: int = 0

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

    personality_traits: str = ""
    ideals: str = ""
    bonds: str = ""
    flaws: str = ""

    money_gold: int = 0
    money_silver: int = 0
    money_copper: int = 0


class CharacterCreate(CharacterBase):
    """
    One-shot creation payload for a level-1 character. ``level`` and HP
    are server-derived; ``extra="forbid"`` rejects unknown/stale fields.
    """

    model_config = ConfigDict(extra="forbid")

    name: CharacterName

    armor_class: CombatStat = 10
    shield: CombatStat = 0

    notes: Notes = ""
    personality_traits: PersonalityText = ""
    ideals: PersonalityText = ""
    bonds: PersonalityText = ""
    flaws: PersonalityText = ""

    money_gold: Money = 0
    money_silver: Money = 0
    money_copper: Money = 0

    strength: int = Field(default=10, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    dexterity: int = Field(default=10, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    constitution: int = Field(default=10, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    intelligence: int = Field(default=10, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    wisdom: int = Field(default=10, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    charisma: int = Field(default=10, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)

    skill_ids: list[int] = Field(default_factory=list, max_length=50)
    item_choice_ids: list[int] = Field(default_factory=list, max_length=50)
    suggestion_ids: list[int] = Field(default_factory=list, max_length=10)

    @field_validator("skill_ids")
    def validate_unique_skill_ids(cls, skill_ids):
        """Reject lists containing duplicate skill IDs."""

        if len(skill_ids) != len(set(skill_ids)):
            raise ValueError("Duplicate skill IDs are not allowed.")

        return skill_ids

    @field_validator("suggestion_ids")
    def validate_unique_suggestion_ids(cls, suggestion_ids):
        """Reject lists containing duplicate suggestion IDs."""

        if len(suggestion_ids) != len(set(suggestion_ids)):
            raise ValueError("Duplicate suggestion IDs are not allowed.")

        return suggestion_ids

    @field_validator("item_choice_ids")
    def validate_unique_item_choice_ids(cls, item_choice_ids):
        """Reject lists containing duplicate item-choice option IDs."""

        if len(item_choice_ids) != len(set(item_choice_ids)):
            raise ValueError("Duplicate item choice IDs are not allowed.")

        return item_choice_ids


class CharacterUpdate(PatchModel):
    """
    All fields optional — only provided fields are updated (PATCH semantics);
    an explicit ``null`` is a 422. Class/race/background, level, and base
    ability scores are not editable here. ``inspiration`` can only be raised
    by a GM (a player may spend it down).
    """

    name: CharacterName | None = None

    current_hp: int | None = Field(default=None, ge=0, le=HP_LIMIT)
    temp_hp: int | None = Field(default=None, ge=0, le=HP_LIMIT)

    armor_class: CombatStat | None = None
    shield: CombatStat | None = None
    speed: CombatStat | None = None

    inspiration: int | None = Field(default=None, ge=0, le=INSPIRATION_MAX)

    notes: Notes | None = None

    personality_traits: PersonalityText | None = None
    ideals: PersonalityText | None = None
    bonds: PersonalityText | None = None
    flaws: PersonalityText | None = None

    money_gold: Money | None = None
    money_silver: Money | None = None
    money_copper: Money | None = None


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


class CharacterResponse(CharacterBase):
    """
    Aggregates response schemas from every sub-domain into one payload.
    Base ability scores are excluded from output; ``hit_dice`` is derived
    from the class on every read. ``speed`` is seeded from the race at
    creation and is plain editable state after that (see
    ``CharacterUpdate.speed``), not recomputed from the race on every read.
    Proficiencies (skills, saving throws, armor, weapons) and granted
    spells are NOT included here — see
    ``GET /characters/{id}/proficiencies`` and
    ``GET /characters/{id}/spells``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int

    level: int
    current_hp: int
    max_hp: int
    temp_hp: int
    inspiration: int = 0

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

    # Filled by ``CharacterService`` when serializing (hit dice from the class); ``speed`` is a plain column.
    hit_dice: str = ""
    speed: int = 30

    ability_scores: AbilityScoresResponse | None = None
