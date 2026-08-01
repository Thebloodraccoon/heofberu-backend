from pydantic import BaseModel, ConfigDict

from app.constants import AbilityScore
from app.features.characters.attacks.schemas import AttackResponse
from app.features.characters.proficiencies.schemas import (
    SavingThrowProficiencyResponse,
    SkillProficiencyResponse,
)
from app.features.characters.spells.schemas import SpellSlotResponse


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
    """
    All fields optional — only provided fields are updated (PATCH semantics).

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


class CharacterResponse(CharacterBase):
    """
    Aggregates response schemas from every sub-domain into one payload.

    This is the one place the sub-domains' schemas are pulled together —
    each sub-domain package otherwise stays independent of the others.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    skill_proficiencies: list[SkillProficiencyResponse] = []
    saving_throw_proficiencies: list[SavingThrowProficiencyResponse] = []
    spell_slots: list[SpellSlotResponse] = []
    attacks: list[AttackResponse] = []
