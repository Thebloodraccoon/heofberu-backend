"""Character grant schemas: choice-answering payloads and pending-group views."""

from pydantic import BaseModel, ConfigDict, Field

from app.constants import AbilityScore, ArmorProficiency, ChoiceType, WeaponProficiency
from app.features.features.effects.schemas import (
    AbilityEffectItem,
    ArmorEffectItem,
    SavingThrowEffectItem,
    SkillEffectItem,
    SpellEffectItem,
    WeaponEffectItem,
)
from app.features.spells.crud.schemas import SpellResponse


class ChoiceAnswerItem(BaseModel):
    """One picked option inside one answered choice group."""

    choice_group_id: int
    choice_option_id: int
    # Required iff the option carries an open ("any skill") skill effect:
    # the concrete skill the player resolved it to.
    skill_id: int | None = None
    # Required iff the option carries an open (school+level-filtered) spell
    # effect: the concrete spell the player resolved it to.
    spell_id: int | None = None


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
    feature's catalog definition. Carries no label of its own; the group's
    own ``label`` names the overall decision.
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
    label: str = ""
    choice_type: ChoiceType
    options: list[PendingChoiceOption] = []


class PendingChoiceGroupsResponse(BaseModel):
    """The pending choice surface of one granted feature."""

    character_feature_id: int
    feature_id: int
    feature_name: str = ""
    groups: list[PendingChoiceGroup] = []


class CharacterSavingThrowProficiencyResponse(BaseModel):
    """A materialized saving-throw proficiency on the character."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore


class CharacterArmorProficiencyResponse(BaseModel):
    """A materialized armor proficiency on the character."""

    model_config = ConfigDict(from_attributes=True)

    armor_type: ArmorProficiency


class CharacterWeaponProficiencyResponse(BaseModel):
    """A materialized weapon proficiency on the character (category or item)."""

    model_config = ConfigDict(from_attributes=True)

    weapon_category: WeaponProficiency | None = None
    item_id: int | None = None


class CharacterGrantedSpellResponse(BaseModel):
    """
    A spell granted to the character, with its full spell record. ``id`` is
    the grant row's own id — pass it as ``granted_spell_id`` to
    ``DELETE /gm-panel/spells`` to revoke a free-form (GM-granted) one.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    spell_id: int
    spell: SpellResponse


class GrantedSkillEffectResponse(BaseModel):
    """A skill proficiency materialized by a grant."""

    model_config = ConfigDict(from_attributes=True)

    skill_id: int
    is_expertise: bool


class GrantEffectsResponse(BaseModel):
    """
    Every materialized effect row a single grant produced on the character —
    what it actually did, resolved (an "any skill" pick already carries the
    concrete ``skill_id``, an open spell filter the concrete ``spell_id``).
    """

    skills: list[GrantedSkillEffectResponse] = []
    saving_throws: list[CharacterSavingThrowProficiencyResponse] = []
    armor: list[CharacterArmorProficiencyResponse] = []
    weapons: list[CharacterWeaponProficiencyResponse] = []
    spells: list[CharacterGrantedSpellResponse] = []


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
