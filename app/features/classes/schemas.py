"""Request/response schemas for the class endpoints."""

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.constants import AbilityScore, DiceType, SpellLevel


class ClassBase(BaseModel):
    """Base class fields shared by create, update, and response schemas."""

    name: str
    hit_dice: DiceType
    skill_choice_count: int = 2
    spellcasting_ability: AbilityScore | None
    description: str = ""
    is_homebrew: bool = False


def _validate_unique_primary_abilities(primary_abilities: list[AbilityScore]) -> list[AbilityScore]:
    if len(primary_abilities) != len(set(primary_abilities)):
        raise ValueError("Duplicate primary abilities are not allowed.")
    return primary_abilities


def _validate_unique_saving_throws(saving_throws: list[AbilityScore]) -> list[AbilityScore]:
    if len(saving_throws) != len(set(saving_throws)):
        raise ValueError("Duplicate saving throws are not allowed.")
    return saving_throws


def _validate_unique_skill_ids(skill_ids: list[int]) -> list[int]:
    if len(skill_ids) != len(set(skill_ids)):
        raise ValueError("Duplicate skill IDs are not allowed.")
    return skill_ids


class ClassCreate(ClassBase):
    """
    Create payload for a class.

    ``primary_abilities`` and ``saving_throws`` default to empty lists
    (matching prior behavior); ``available_skills`` is optional — a class
    can be created without granting any skill choices up front, or with
    them supplied immediately, avoiding an extra PUT round-trip. When
    provided, ``available_skills`` semantics are "full replace from
    empty", same as the dedicated
    ``PUT /classes/{class_id}/available-skills`` endpoint.

    If ``spellcasting_ability`` is set (non-null), it must appear in
    ``primary_abilities`` — a class's casting stat is expected to also be
    one of its primary abilities. A non-caster class must pass
    ``spellcasting_ability: null`` explicitly and does not need it in
    ``primary_abilities``.
    """

    primary_abilities: list[AbilityScore] = []
    saving_throws: list[AbilityScore] = []
    available_skills: list[int] | None = None

    @field_validator("primary_abilities")
    def validate_unique_primary_abilities(cls, primary_abilities):
        """Reject lists containing duplicate abilities."""
        return _validate_unique_primary_abilities(primary_abilities)

    @field_validator("saving_throws")
    def validate_unique_saving_throws(cls, saving_throws):
        """Reject lists containing duplicate abilities."""
        return _validate_unique_saving_throws(saving_throws)

    @field_validator("available_skills")
    def validate_unique_available_skills(cls, available_skills):
        """Reject lists containing duplicate skill IDs."""
        if available_skills is None:
            return available_skills
        return _validate_unique_skill_ids(available_skills)

    @model_validator(mode="after")
    def validate_spellcasting_ability_is_primary(self):
        """Ensure a non-null ``spellcasting_ability`` is also a primary ability."""
        if self.spellcasting_ability is not None and self.spellcasting_ability not in self.primary_abilities:
            raise ValueError(
                f"spellcasting_ability '{self.spellcasting_ability}' must also appear in primary_abilities."
            )
        return self


class ClassUpdate(BaseModel):
    """
    All fields optional — only provided fields are updated (PATCH semantics).

    Deliberately does NOT include ``available_skills``: that keeps its own
    PUT endpoint with explicit full-replace semantics, since PATCH's "only
    touch what's set" doesn't map cleanly onto "replace the whole list"
    (same rationale as Race's ability_bonuses/granted_skills).

    ``primary_abilities`` and ``saving_throws`` ARE included here (unlike
    Race's ability_bonuses/granted_skills) because they're simple string
    lists rather than rows with extra data, so a full-replace PATCH field
    is unambiguous.

    Note on ``spellcasting_ability`` + ``primary_abilities``: if
    ``primary_abilities`` is included in the request but
    ``spellcasting_ability`` is not, the service layer checks the class's
    *current* ``spellcasting_ability`` (if any) still appears in the new
    ``primary_abilities`` list — and rejects the update if it doesn't, to
    avoid silently leaving a caster class with a casting ability that's no
    longer one of its primary abilities. Pass ``spellcasting_ability``
    explicitly in the same request to change it instead.
    """

    name: str | None = None
    hit_dice: DiceType | None = None
    skill_choice_count: int | None = None
    spellcasting_ability: AbilityScore | None = None
    description: str | None = None
    is_homebrew: bool | None = None
    primary_abilities: list[AbilityScore] | None = None
    saving_throws: list[AbilityScore] | None = None

    @field_validator("primary_abilities")
    def validate_unique_primary_abilities(cls, primary_abilities):
        """Reject lists containing duplicate abilities."""
        if primary_abilities is None:
            return primary_abilities
        return _validate_unique_primary_abilities(primary_abilities)

    @field_validator("saving_throws")
    def validate_unique_saving_throws_update(cls, saving_throws):
        """Reject lists containing duplicate abilities."""
        if saving_throws is None:
            return saving_throws
        return _validate_unique_saving_throws(saving_throws)

    @model_validator(mode="after")
    def validate_spellcasting_ability_is_primary_if_both_set(self):
        """Ensure a non-null ``spellcasting_ability`` is primary when both are provided."""
        if (
            self.spellcasting_ability is not None
            and self.primary_abilities is not None
            and self.spellcasting_ability not in self.primary_abilities
        ):
            raise ValueError(
                f"spellcasting_ability '{self.spellcasting_ability}' must also appear in primary_abilities."
            )
        return self


class SavingThrowsUpdate(BaseModel):
    """Full replacement list of saving throw proficiencies for a class."""

    saving_throws: list[AbilityScore]

    @field_validator("saving_throws")
    def validate_unique_saving_throws(cls, saving_throws):
        """Reject lists containing duplicate abilities."""
        return _validate_unique_saving_throws(saving_throws)


class AvailableSkillsUpdate(BaseModel):
    """Full replacement list of skill IDs a class may choose proficiencies from."""

    skill_ids: list[int]

    @field_validator("skill_ids")
    def validate_unique_skill_ids(cls, skill_ids):
        """Reject lists containing duplicate skill IDs."""
        return _validate_unique_skill_ids(skill_ids)


class SpellSlotEntry(BaseModel):
    """One row of a spell slot progression: slots of a given spell level at a given class level."""

    spell_level: SpellLevel
    slots: int = 0


class SpellSlotProgressionUpdate(BaseModel):
    """
    Full replacement of the spell slots a class grants at a single
    ``class_level``, keyed by ``spell_level`` — e.g. a level-5 Wizard's
    slots across LEVEL_1..LEVEL_3.

    Full replace, not merge: any ``spell_level`` for this ``class_level``
    not included in ``slots`` is removed (slots reset to 0). Duplicate
    ``spell_level`` entries are rejected — send one entry per spell level.

    No relationship is enforced to ``spellcasting_ability`` — progressions
    may be set on any class, including non-casters, to support cases like
    multiclass slot tables that don't map onto a single ability.
    """

    slots: list[SpellSlotEntry]

    @field_validator("slots")
    def validate_unique_spell_levels(cls, slots):
        """Reject lists containing duplicate ``spell_level`` entries."""
        levels = [entry.spell_level for entry in slots]
        if len(levels) != len(set(levels)):
            raise ValueError("Duplicate spell_level entries are not allowed.")
        return slots


class SpellSlotProgressionResponse(BaseModel):
    """Spell slots granted at one class level, as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    class_level: int
    spell_level: SpellLevel
    slots: int


class PrimaryAbilityResponse(BaseModel):
    """A class's primary ability score, as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore


class SavingThrowResponse(BaseModel):
    """A class's saving throw proficiency, as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore


class SkillResponse(BaseModel):
    """Brief skill representation embedded in class responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    name: str
    ability: AbilityScore
    description: str


class ClassResponse(ClassBase):
    """Full class representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by_id: int | None = None
    primary_abilities: list[PrimaryAbilityResponse] = []
    saving_throws: list[SavingThrowResponse] = []
    available_skills: list[SkillResponse] = []
    spell_slot_progression: list[SpellSlotProgressionResponse] = []


class ClassBriefResponse(BaseModel):
    """Lightweight listing row"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    hit_dice: DiceType
    is_homebrew: bool = False
