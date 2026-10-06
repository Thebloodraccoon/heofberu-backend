"""Character grant schemas: choice-answering payloads and pending-group views."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.constants import AbilityScore, ArmorProficiency, ChoiceType, WeaponProficiency
from app.core.types import EntityId
from app.features.characters.spells.schemas import CharacterSpellResponse
from app.features.features.effects.schemas import EffectGroup

# Upper bound on the answers of one request (a feature has a handful of groups).
MAX_ANSWERS = 50


class ChoiceAnswerItem(BaseModel):
    """
    One picked option inside one answered choice group.

    No ``skill_id``/``spell_id`` field: picking an option that carries an
    open ("any skill"/"any spell") effect isn't supported yet — the answer
    is rejected (``SkillResolutionsError``/``SpellResolutionsError``, 422)
    regardless of what's requested.
    """

    choice_group_id: EntityId
    choice_option_id: EntityId


class GrantChoicesUpdate(BaseModel):
    """
    Player's (re)answer for the pending choice groups of one granted feature.

    ``answers`` must include exactly ``pick_count`` items per group that the
    feature still needs answered (unanswered groups stay pending). Re-answers
    replace the group's stored picks in the same transaction.
    """

    model_config = ConfigDict(extra="forbid")

    answers: list[ChoiceAnswerItem] = Field(default_factory=list, max_length=MAX_ANSWERS)


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
    effects: list[EffectGroup] = Field(default_factory=list)


class PendingChoiceGroup(BaseModel):
    """A grant's choice group that still needs the player's picks."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    pick_count: int
    choice_type: ChoiceType
    options: list[PendingChoiceOption] = Field(default_factory=list)


class PendingChoiceGroupsResponse(BaseModel):
    """The pending choice surface of one granted feature."""

    character_feature_id: int
    feature_id: int
    feature_name: str = ""
    groups: list[PendingChoiceGroup] = Field(default_factory=list)


class CharacterSavingThrowProficiencyResponse(BaseModel):
    """A saving-throw proficiency on the character."""

    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore


class CharacterArmorProficiencyResponse(BaseModel):
    """An armor proficiency on the character."""

    model_config = ConfigDict(from_attributes=True)

    armor_type: ArmorProficiency


class CharacterWeaponProficiencyResponse(BaseModel):
    """A weapon proficiency on the character (category or item)."""

    model_config = ConfigDict(from_attributes=True)

    weapon_category: WeaponProficiency | None = None
    item_id: int | None = None


class GrantedSkillEffectResponse(BaseModel):
    """A skill proficiency a grant gives."""

    model_config = ConfigDict(from_attributes=True)

    skill_id: int
    is_expertise: bool


class GrantedAbilityEffectResponse(BaseModel):
    """An ability-score effect a grant gives (display only — totals come from the stats cache)."""

    ability: AbilityScore
    amount: int
    new_cap: int | None = None


class GrantedAbilityGroup(BaseModel):
    """Ability-score effects of a grant."""

    effect_type: Literal["ability"]
    items: list[GrantedAbilityEffectResponse]


class GrantedSkillGroup(BaseModel):
    """Skill proficiencies of a grant (expertise merged across its sources)."""

    effect_type: Literal["skill"]
    items: list[GrantedSkillEffectResponse]


class GrantedSavingThrowGroup(BaseModel):
    """Saving-throw proficiencies of a grant."""

    effect_type: Literal["saving_throw"]
    items: list[CharacterSavingThrowProficiencyResponse]


class GrantedArmorGroup(BaseModel):
    """Armor proficiencies of a grant."""

    effect_type: Literal["armor"]
    items: list[CharacterArmorProficiencyResponse]


class GrantedWeaponGroup(BaseModel):
    """Weapon proficiencies of a grant."""

    effect_type: Literal["weapon"]
    items: list[CharacterWeaponProficiencyResponse]


class GrantedSpellGroup(BaseModel):
    """Spells a grant gives, as full spell records."""

    effect_type: Literal["spell"]
    items: list[CharacterSpellResponse]


# What a single grant gives the character — its feature's fixed effects plus the picked options'
# bundles, computed from the current effect tree — in the same ``{effect_type, items}`` shape as
# ``EffectGroup``, only non-empty types, but with resolved items (deduplicated, spells expanded).
GrantEffectGroup = Annotated[
    GrantedAbilityGroup
    | GrantedSkillGroup
    | GrantedSavingThrowGroup
    | GrantedArmorGroup
    | GrantedWeaponGroup
    | GrantedSpellGroup,
    Field(discriminator="effect_type"),
]


class ChosenOptionResponse(BaseModel):
    """One of the player's stored picks for a grant's choice group, with the option's non-empty effect groups."""

    choice_group_id: int
    choice_option_id: int
    effects: list[EffectGroup] = Field(default_factory=list)


class AnsweredChoicesResponse(BaseModel):
    """The player's resolved picks for one granted feature's choice groups — the answered side of ``PendingChoiceGroupsResponse``."""

    character_feature_id: int
    feature_id: int
    feature_name: str = ""
    choices: list[ChosenOptionResponse] = Field(default_factory=list)
