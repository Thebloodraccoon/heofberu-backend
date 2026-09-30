"""Character grant schemas: choice-answering payloads and pending-group views."""

from pydantic import BaseModel, ConfigDict, Field

from app.constants import AbilityScore, ArmorProficiency, ChoiceType, WeaponProficiency
from app.features.characters.spells.schemas import CharacterSpellResponse
from app.features.features.effects.schemas import (
    AbilityEffectItem,
    ArmorEffectItem,
    SavingThrowEffectItem,
    SkillEffectItem,
    SpellEffectItem,
    WeaponEffectItem,
)


class ChoiceAnswerItem(BaseModel):
    """
    One picked option inside one answered choice group.

    No ``skill_id``/``spell_id`` field: picking an option that carries an
    open ("any skill"/"any spell") effect isn't supported yet — the answer
    is rejected (``SkillResolutionsError``/``SpellResolutionsError``, 422)
    regardless of what's requested.
    """

    choice_group_id: int
    choice_option_id: int


class GrantChoicesUpdate(BaseModel):
    """
    Player's (re)answer for the pending choice groups of one granted feature.

    ``answers`` must include exactly ``pick_count`` items per group that the
    feature still needs answered (unanswered groups stay pending). Re-answers
    replace the group's stored picks and re-materialize the affected effect
    rows on the character in the same transaction.
    """

    model_config = ConfigDict(extra="forbid")

    answers: list[ChoiceAnswerItem] = Field(default_factory=list)


class PendingChoiceOption(BaseModel):
    """
    A pending option inside a pending choice group, with its open-effect
    flags and its full effect bundle — so a client can render what the
    option actually does (e.g. "+1 STR") without a separate fetch of the
    feature's catalog definition.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    needs_skill: bool = False
    needs_spell: bool = False
    ability_effects: list[AbilityEffectItem] = []
    skill_effects: list[SkillEffectItem] = []
    saving_throw_effects: list[SavingThrowEffectItem] = []
    armor_effects: list[ArmorEffectItem] = []
    weapon_effects: list[WeaponEffectItem] = []
    spell_effects: list[SpellEffectItem] = []


class PendingChoiceGroup(BaseModel):
    """A grant's choice group that still needs the player's picks."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    pick_count: int
    choice_type: ChoiceType
    options: list[PendingChoiceOption] = []


class PendingChoiceGroupsResponse(BaseModel):
    """The pending choice surface of one granted feature."""

    character_feature_id: int
    feature_id: int
    feature_name: str = ""
    groups: list[PendingChoiceGroup] = []


class CharacterSavingThrowProficiencyResponse(BaseModel):
    """Asaving-throw proficiency on the character."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore


class CharacterArmorProficiencyResponse(BaseModel):
    """Aarmor proficiency on the character."""

    model_config = ConfigDict(from_attributes=True)

    armor_type: ArmorProficiency


class CharacterWeaponProficiencyResponse(BaseModel):
    """Aweapon proficiency on the character (category or item)."""

    model_config = ConfigDict(from_attributes=True)

    weapon_category: WeaponProficiency | None = None
    item_id: int | None = None


class GrantedSkillEffectResponse(BaseModel):
    """A skill proficiency a grant gives."""

    model_config = ConfigDict(from_attributes=True)

    skill_id: int
    is_expertise: bool


class GrantEffectsResponse(BaseModel):
    """
    What a single grant gives the character — its feature's fixed effects
    plus the picked options' bundles, computed from the current effect tree.
    """

    skills: list[GrantedSkillEffectResponse] = []
    saving_throws: list[CharacterSavingThrowProficiencyResponse] = []
    armor: list[CharacterArmorProficiencyResponse] = []
    weapons: list[CharacterWeaponProficiencyResponse] = []
    spells: list[CharacterSpellResponse] = []


class ChosenOptionResponse(BaseModel):
    """One of the player's stored picks for a grant's choice group, with the option's effect bundle."""

    choice_group_id: int
    choice_option_id: int
    ability_effects: list[AbilityEffectItem] = []
    skill_effects: list[SkillEffectItem] = []
    saving_throw_effects: list[SavingThrowEffectItem] = []
    armor_effects: list[ArmorEffectItem] = []
    weapon_effects: list[WeaponEffectItem] = []
    spell_effects: list[SpellEffectItem] = []


class AnsweredChoicesResponse(BaseModel):
    """The player's resolved picks for one granted feature's choice groups — the answered side of ``PendingChoiceGroupsResponse``."""

    character_feature_id: int
    feature_id: int
    feature_name: str = ""
    choices: list[ChosenOptionResponse] = []
