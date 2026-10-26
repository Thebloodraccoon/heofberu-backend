"""Character grant schemas: choice-answering payloads and pending-group views."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.constants import (
    AbilityScore,
    ArmorProficiency,
    ChoiceType,
    SkillEffectMode,
    SpellLevel,
    SpellSchool,
    WeaponProficiency,
)
from app.core.types import EntityId
from app.features.characters.spells.schemas import CharacterSpellResponse
from app.features.features.effects.schemas import ArmorClassEffectItem, EffectGroup, SpeedEffectItem

# Upper bound on the answers of one request (a feature has a handful of groups).
MAX_ANSWERS = 50


class ChoiceAnswerItem(BaseModel):
    """
    One picked option inside one answered choice group.

    ``skill_id`` names the skill for an option with an open ("any skill")
    skill effect, ``spell_id`` the spell for an option with an open ("any
    spell") spell effect, ``ability`` the ability for an option with an open
    ("any ability" / "any saving throw") effect, ``item_id`` the tool for an
    option with an open ("any tool") tool effect — required there, rejected on
    any other option (422). The same open option may be picked several times
    in one group, each time with a different skill/spell/ability/tool.
    """

    choice_group_id: EntityId
    choice_option_id: EntityId
    skill_id: EntityId | None = None
    spell_id: EntityId | None = None
    ability: AbilityScore | None = None
    item_id: EntityId | None = None


class GrantChoicesUpdate(BaseModel):
    """
    Player's (re)answer for the pending choice groups of one granted feature.

    ``answers`` must include exactly ``pick_count`` items per group that the
    feature still needs answered (unanswered groups stay pending). Re-answers
    replace the group's stored picks in the same transaction.
    """

    model_config = ConfigDict(extra="forbid")

    answers: list[ChoiceAnswerItem] = Field(default_factory=list, max_length=MAX_ANSWERS)


class SpellPickCandidate(BaseModel):
    """A spell an open ("any spell") option may be picked with — enough to list and search it."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    level: SpellLevel
    school: SpellSchool
    is_ritual: bool = False


class ItemPickCandidate(BaseModel):
    """A tool an open ("any tool") option may be picked with."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class PendingChoiceOption(BaseModel):
    """
    A pending option inside a pending choice group, with its open-effect
    flags and its full effect bundle — so a client can render what the
    option actually does (e.g. "+1 STR") without a separate fetch of the
    feature's catalog definition.

    Skill options are checked against the character's other sources:
    ``allowed_skill_ids`` (open options only) lists the skills it may be
    picked with right now; ``available`` is ``False`` for a concrete option
    the character can't take (e.g. expertise in a skill it isn't proficient
    in, or proficiency it already has) and for an open option with no
    allowed skill.

    An open spell option lists in ``allowed_spells`` (by level, then name)
    every spell that passes its filter and that the character doesn't have
    yet; ``available`` is ``False`` when there is none.

    ``needs_ability``: an open ability-score / saving-throw option — answer it with ``ability``
    (any ability the option doesn't already name).

    ``needs_item``: an open tool option — answer it with ``item_id``, one of ``allowed_items`` (the tools
    of the option's category the character isn't proficient with through another grant).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    needs_skill: bool = False
    needs_spell: bool = False
    needs_ability: bool = False
    needs_item: bool = False
    allowed_skill_ids: list[int] | None = None
    allowed_spells: list[SpellPickCandidate] | None = None
    allowed_items: list[ItemPickCandidate] | None = None
    available: bool = True
    effects: list[EffectGroup] = Field(default_factory=list)


class PendingChoiceGroup(BaseModel):
    """A grant's choice group that still needs the player's picks."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    pick_count: int
    choice_type: ChoiceType
    options: list[PendingChoiceOption] = Field(default_factory=list)


class PendingChoicesCountResponse(BaseModel):
    """How many of a character's grants still have unanswered choice groups (the light badge read)."""

    count: int


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
    """An armor proficiency on the character (category or item)."""

    model_config = ConfigDict(from_attributes=True)

    armor_type: ArmorProficiency | None = None
    item_id: int | None = None


class CharacterWeaponProficiencyResponse(BaseModel):
    """A weapon proficiency on the character (category or item)."""

    model_config = ConfigDict(from_attributes=True)

    weapon_category: WeaponProficiency | None = None
    item_id: int | None = None


class CharacterToolProficiencyResponse(BaseModel):
    """A tool proficiency on the character (a ``TOOL`` item)."""

    model_config = ConfigDict(from_attributes=True)

    item_id: int


class GrantedSkillEffectResponse(BaseModel):
    """
    What a grant gives in one skill. ``mode`` is its effects folded into one
    (``EXPERTISE``: expertise only, effective while another source gives the
    proficiency; ``UPGRADE``: proficiency, or expertise on top of another
    source); ``is_expertise`` is the expertise the grant gives on its own.
    The character's resolved result is ``GET /characters/{id}/proficiencies``.
    """

    model_config = ConfigDict(from_attributes=True)

    skill_id: int
    is_expertise: bool
    mode: SkillEffectMode = SkillEffectMode.PROFICIENCY


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


class GrantedToolGroup(BaseModel):
    """Tool proficiencies of a grant."""

    effect_type: Literal["tool"]
    items: list[CharacterToolProficiencyResponse]


class GrantedSpeedGroup(BaseModel):
    """Speed effects of a grant, as defined (applied by the character's combat stats)."""

    effect_type: Literal["speed"]
    items: list[SpeedEffectItem]


class GrantedArmorClassGroup(BaseModel):
    """AC effects of a grant, as defined (applied by the character's combat stats)."""

    effect_type: Literal["armor_class"]
    items: list[ArmorClassEffectItem]


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
    | GrantedToolGroup
    | GrantedSpellGroup
    | GrantedSpeedGroup
    | GrantedArmorClassGroup,
    Field(discriminator="effect_type"),
]


class ChosenOptionResponse(BaseModel):
    """
    One of the player's stored picks for a grant's choice group, with the option's non-empty effect groups
    and, for an open ("any skill/spell/ability") option, the skill/spell/ability named for it.
    """

    choice_group_id: int
    choice_option_id: int
    picked_skill_id: int | None = None
    picked_spell_id: int | None = None
    picked_ability: AbilityScore | None = None
    picked_item_id: int | None = None
    effects: list[EffectGroup] = Field(default_factory=list)


class AnsweredChoicesResponse(BaseModel):
    """The player's resolved picks for one granted feature's choice groups — the answered side of ``PendingChoiceGroupsResponse``."""

    character_feature_id: int
    feature_id: int
    feature_name: str = ""
    choices: list[ChosenOptionResponse] = Field(default_factory=list)
