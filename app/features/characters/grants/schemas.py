"""Character grant schemas: choice-answering payloads and pending-group views."""

from pydantic import BaseModel, ConfigDict, Field

from app.constants import AbilityScore, ArmorProficiency, WeaponProficiency


class ChoiceAnswerItem(BaseModel):
    """One picked option inside one answered choice group."""

    choice_group_id: int
    choice_option_id: int
    # Required iff the option carries an open ("any skill") skill effect:
    # the concrete skill the player resolved it to.
    skill_id: int | None = None


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
    """A pending option inside a pending choice group, with its open-skill flag."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str = ""
    needs_skill: bool = False


class PendingChoiceGroup(BaseModel):
    """A grant's choice group that still needs the player's picks."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    pick_count: int
    label: str = ""
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
    """A spell granted to the character by a feature/feat."""

    model_config = ConfigDict(from_attributes=True)

    spell_id: int
    always_prepared: bool = True
    counts_against_known_limit: bool = False
