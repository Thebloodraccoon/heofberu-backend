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

    Skill proficiencies, saving throw proficiencies, spell slots, and
    known spells are managed through their own dedicated endpoints, not
    through this schema.

    If ``class_id``/``race_id``/``background_id`` are included, they are
    re-validated for existence the same as on create.

    ``class_id`` is intentionally typed as plain ``int`` (not ``int |
    None``): the field can be omitted from the request (in which case it
    keeps its current value — PATCH semantics via ``exclude_unset``), but
    it cannot be explicitly set to ``null``, since ``Character.class_id``
    is a required, non-nullable column. Sending ``"class_id": null``
    is rejected with a 422 at the schema layer rather than reaching the
    service and failing as a DB ``IntegrityError``. ``race_id`` and
    ``background_id`` remain ``int | None`` since those columns are
    nullable — explicitly clearing them is a valid operation.
    """

    name: str | None = None
    image_path: str | None = None
    level: int | None = Field(default=None, ge=1, le=20)

    class_id: int = None
    subclass: str | None = None
    race_id: int | None = None
    background_id: int | None = None

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

    strength: int | None = Field(default=None, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    dexterity: int | None = Field(default=None, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    constitution: int | None = Field(default=None, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    intelligence: int | None = Field(default=None, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    wisdom: int | None = Field(default=None, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)
    charisma: int | None = Field(default=None, ge=ABILITY_SCORE_MIN, le=ABILITY_SCORE_MAX)

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
    and the computed result. It's optional in the response only because
    a freshly-created character may not have a cache row yet on some
    codepaths (e.g. serialized before the first recalculation) —
    ``CharacterService`` always populates it after create/update/get by ID.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    ability_scores: AbilityScoresResponse | None = None
    skill_proficiencies: list[SkillProficiencyResponse] = []
    saving_throw_proficiencies: list[SavingThrowProficiencyResponse] = []
    spell_slots: list[SpellSlotResponse] = []
    attacks: list[AttackResponse] = []
