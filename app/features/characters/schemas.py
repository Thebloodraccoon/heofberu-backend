from pydantic import BaseModel, ConfigDict

from app.constants import AbilityScore
from app.features.spells.schemas import SpellResponse


class CharacterBase(BaseModel):
    name: str
    image_path: str | None = None
    level: int = 1

    class_id: int
    subclass: str = ""
    race_id: int | None = None

    current_hp: int = 0
    max_hp: int = 0
    temp_hp: int = 0
    hit_dice: str = ""
    speed: int = 30
    armor_class: int = 10
    shield: int = 0
    initiative_bonus: int = 0
    passive_perception_bonus: int = 0
    has_jack_of_all_trades: bool = False

    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10

    proficiencies: str = ""

    traits: str = ""
    feats: str = ""
    inventory: str = ""
    backstory: str = ""
    notes: str = ""

    money_gold: int = 0
    money_silver: int = 0
    money_copper: int = 0

    spell_ability: AbilityScore | None = None
    spell_dc_misc_bonus: int = 0
    spell_attack_misc_bonus: int = 0


class CharacterCreate(CharacterBase):
    pass


class CharacterUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics).

    Skill proficiencies, saving throw proficiencies, and spell slots are
    managed through their own dedicated endpoints, not through this schema.
    """

    name: str | None = None
    image_path: str | None = None
    level: int | None = None

    class_id: int | None = None
    subclass: str | None = None
    race_id: int | None = None

    current_hp: int | None = None
    max_hp: int | None = None
    temp_hp: int | None = None
    hit_dice: str | None = None
    speed: int | None = None
    armor_class: int | None = None
    shield: int | None = None
    initiative_bonus: int | None = None
    passive_perception_bonus: int | None = None
    has_jack_of_all_trades: bool | None = None

    strength: int | None = None
    dexterity: int | None = None
    constitution: int | None = None
    intelligence: int | None = None
    wisdom: int | None = None
    charisma: int | None = None

    proficiencies: str | None = None

    traits: str | None = None
    feats: str | None = None
    inventory: str | None = None
    backstory: str | None = None
    notes: str | None = None

    money_gold: int | None = None
    money_silver: int | None = None
    money_copper: int | None = None

    spell_ability: AbilityScore | None = None
    spell_dc_misc_bonus: int | None = None
    spell_attack_misc_bonus: int | None = None


class HpUpdate(BaseModel):
    """Update a character's HP either by a relative delta or by setting
    absolute values. Provide either `delta` or one/both of
    `current_hp`/`temp_hp` — not both styles at once.
    """

    delta: int | None = None
    current_hp: int | None = None
    temp_hp: int | None = None


class SkillProficiencyItem(BaseModel):
    skill_id: int
    is_expertise: bool = False


class SkillProficienciesUpdate(BaseModel):
    """Full replacement list of a character's skill proficiencies."""

    skill_proficiencies: list[SkillProficiencyItem]


class SavingThrowProficienciesUpdate(BaseModel):
    """Full replacement list of a character's saving throw proficiencies."""

    saving_throws: list[AbilityScore]


class SkillProficiencyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill_id: int
    is_expertise: bool


class SavingThrowProficiencyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ability: AbilityScore


class SpellSlotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    spell_level: str
    total: int
    used: int


class SpellSlotUpdate(BaseModel):
    """Update the used/total count for a single spell slot level."""

    level: str
    used: int | None = None
    total: int | None = None


class RestRequest(BaseModel):
    type: str  # "short" or "long"


class CharacterSpellAdd(BaseModel):
    spell_id: int


class CharacterSpellPrepareUpdate(BaseModel):
    is_prepared: bool


class CharacterSpellResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    spell_id: int
    is_prepared: bool
    spell: SpellResponse


class AttackBase(BaseModel):
    name: str
    attack_type: str  # e.g. MELEE, RANGED, SPELL
    ability: AbilityScore
    is_proficient: bool = True

    bonus_attack: int = 0
    bonus_damage: int = 0
    damage_dice: str = ""
    damage_type: str | None = None
    range: str = ""
    notes: str = ""


class AttackCreate(AttackBase):
    pass


class AttackUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    name: str | None = None
    attack_type: str | None = None
    ability: AbilityScore | None = None
    is_proficient: bool | None = None

    bonus_attack: int | None = None
    bonus_damage: int | None = None
    damage_dice: str | None = None
    damage_type: str | None = None
    range: str | None = None
    notes: str | None = None


class AttackResponse(AttackBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    character_id: int


class RollCheckRequest(BaseModel):
    """Request a skill check or saving throw roll.

    Provide exactly one of `skill_id` (skill check) or `ability` (raw
    ability check or saving throw, depending on `check_type`).
    """

    skill_id: int | None = None
    ability: AbilityScore | None = None
    check_type: str = "check"  # "check" or "save"


class RollCheckResponse(BaseModel):
    d20_roll: int
    ability: AbilityScore
    ability_modifier: int
    proficiency_bonus: int
    is_proficient: bool
    total: int
    check_type: str
    skill_id: int | None = None


class RollAttackRequest(BaseModel):
    attack_id: int


class RollAttackResponse(BaseModel):
    attack_id: int
    attack_name: str
    d20_roll: int
    ability_modifier: int
    proficiency_bonus: int
    is_proficient: bool
    attack_total: int
    damage_dice: str
    damage_roll: int
    damage_modifier: int
    damage_total: int
    is_critical: bool


class CharacterResponse(CharacterBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    skill_proficiencies: list[SkillProficiencyResponse] = []
    saving_throw_proficiencies: list[SavingThrowProficiencyResponse] = []
    spell_slots: list[SpellSlotResponse] = []
    attacks: list[AttackResponse] = []