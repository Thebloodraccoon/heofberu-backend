"""Character schemas, including the aggregated CharacterResponse."""

from pydantic import BaseModel, ConfigDict, Field

from app.constants import AbilityScore
from app.features.characters.attacks.schemas import AttackResponse
from app.features.characters.proficiencies.schemas import (
    SavingThrowProficiencyResponse,
    SkillProficiencyResponse,
)
from app.features.characters.spells.schemas import SpellSlotResponse

# Standard D&D 5e ability-score range for values entered directly by a
# player (before racial/feat bonuses are applied) — matches the typical
# point-buy/standard-array range. Bonuses on top of this (race, feats)
# are computed separately and are not bound by this range themselves.
ABILITY_SCORE_MIN = 3
ABILITY_SCORE_MAX = 18


class CharacterBase(BaseModel):
    """Base character fields shared by create and response schemas."""

    name: str
    image_path: str | None = None
    level: int = Field(default=1, ge=1, le=20)

    class_id: int
    subclass: str = ""
    race_id: int | None = None
    background_id: int | None = None

    current_hp: int = Field(default=0, ge=0)
    max_hp: int = Field(default=0, ge=0)
    temp_hp: int = Field(default=0, ge=0)
    hit_dice: str = ""
    speed: int = 30
    armor_class: int = 10
    shield: int = 0
    initiative_bonus: int = 0
    passive_perception_bonus: int = 0
    has_jack_of_all_trades: bool = False

    # Base ability scores — what the player entered, before racial or
    # feat bonuses. Effective (post-bonus) totals are exposed separately
    # on CharacterResponse via the ability_scores field.
    strength: int = Field(default=10, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    dexterity: int = Field(default=10, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    constitution: int = Field(default=10, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    intelligence: int = Field(default=10, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    wisdom: int = Field(default=10, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    charisma: int = Field(default=10, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)

    proficiencies: str = ""

    traits: str = ""
    backstory: str = ""
    notes: str = ""

    personality_traits: str = ""
    ideals: str = ""
    bonds: str = ""
    flaws: str = ""

    money_gold: int = Field(default=0, ge=0)
    money_silver: int = Field(default=0, ge=0)
    money_copper: int = Field(default=0, ge=0)

    spell_ability: AbilityScore | None = None
    spell_dc_misc_bonus: int = 0
    spell_attack_misc_bonus: int = 0


class CharacterCreate(CharacterBase):
    """
    Create payload for a character.

    ``class_id`` is required and must reference an existing class;
    ``race_id``/``background_id`` are optional but, if provided, must
    also reference existing records. Existence checks happen in
    ``CharacterService.create_character`` (needs DB access, not doable
    at the schema layer) — see ``ClassNotFoundException`` /
    ``RaceNotFoundException`` / ``BackgroundNotFoundException``.
    """


class CharacterUpdate(BaseModel):
    """
    All fields optional — only provided fields are updated (PATCH semantics).

    Skill proficiencies, saving throw proficiencies, spell slots, known
    spells, and attacks are managed through their own dedicated endpoints,
    not through this schema.

    Note: ``class_id``, ``race_id``, and ``background_id`` cannot be
    changed via this schema — a character's class, race, and background
    are set at creation and are not editable here.
    """

    name: str | None = None
    image_path: str | None = None
    level: int | None = Field(default=None, ge=1, le=20)

    current_hp: int | None = Field(default=None, ge=0)
    max_hp: int | None = Field(default=None, ge=0)
    temp_hp: int | None = Field(default=None, ge=0)
    hit_dice: str | None = None
    speed: int | None = None
    armor_class: int | None = None
    shield: int | None = None
    initiative_bonus: int | None = None
    passive_perception_bonus: int | None = None
    has_jack_of_all_trades: bool | None = None

    proficiencies: str | None = None

    traits: str | None = None
    backstory: str | None = None
    notes: str | None = None

    personality_traits: str | None = None
    ideals: str | None = None
    bonds: str | None = None
    flaws: str | None = None

    money_gold: int | None = Field(default=None, ge=0)
    money_silver: int | None = Field(default=None, ge=0)
    money_copper: int | None = Field(default=None, ge=0)

    spell_ability: AbilityScore | None = None
    spell_dc_misc_bonus: int | None = None
    spell_attack_misc_bonus: int | None = None


class AbilityScoresResponse(BaseModel):
    """
    Effective (post-bonus) ability score totals — base value plus race
    and feat bonuses. Backed by the ``character_ability_scores`` cache
    table; see ``CharacterAbilityScoreCalculator`` for how it's computed
    and ``CharacterService.get_character`` for when it's refreshed.
    """

    model_config = ConfigDict(from_attributes=True)

    strength_total: int
    dexterity_total: int
    constitution_total: int
    intelligence_total: int
    wisdom_total: int
    charisma_total: int


class CharacterResponse(CharacterBase):
    """
    Aggregates response schemas from every sub-domain into one payload.

    ``ability_scores`` holds the effective (post-bonus) totals, kept
    distinct from the base ``strength``..``charisma`` fields inherited
    from ``CharacterBase`` so callers can always see both the raw input
    and the computed result. It is optional only on the listing path
    (``CharacterService.get_characters``), which reads the cache as-is
    without recomputing — a character never fetched individually (and so
    with no cache row yet) reports ``None`` here. ``get_character``
    always refreshes before returning, and create/update recompute
    whenever the change can affect ability scores.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    ability_scores: AbilityScoresResponse | None = None
    skill_proficiencies: list[SkillProficiencyResponse] = []
    saving_throw_proficiencies: list[SavingThrowProficiencyResponse] = []
    spell_slots: list[SpellSlotResponse] = []
    attacks: list[AttackResponse] = []
