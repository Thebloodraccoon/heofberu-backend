from pydantic import BaseModel, ConfigDict

from app.constants import AbilityScore


class CharacterBase(BaseModel):
    name: str
    image_path: str | None = None
    level: int = 1

    character_class: str = ""
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
    has_jack_of_all_trades: int = 0

    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10

    skill_proficiencies: dict = {}
    saving_throw_proficiencies: str = ""
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
    spell_slots: dict = {}


class CharacterCreate(CharacterBase):
    pass


class CharacterUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    name: str | None = None
    image_path: str | None = None
    level: int | None = None

    character_class: str | None = None
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
    has_jack_of_all_trades: int | None = None

    strength: int | None = None
    dexterity: int | None = None
    constitution: int | None = None
    intelligence: int | None = None
    wisdom: int | None = None
    charisma: int | None = None

    skill_proficiencies: dict | None = None
    saving_throw_proficiencies: str | None = None
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
    spell_slots: dict | None = None


class CharacterResponse(CharacterBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int