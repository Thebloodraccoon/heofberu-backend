"""Request/response schemas for the class CRUD endpoints (class identity; capability schemas live in their own folders)."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import AbilityScore, ArmorProficiency, DiceType, WeaponProficiency
from app.features.classes.armor.schemas import ArmorProficiencyResponse, _validate_unique_armor_proficiencies
from app.features.classes.progression.schemas import SpellSlotProgressionResponse
from app.features.classes.skills.schemas import SkillResponse
from app.features.classes.throws.schemas import SavingThrowResponse, _validate_unique_saving_throws
from app.features.classes.weapons.schemas import WeaponProficiencyResponse, _validate_unique_weapon_proficiencies
from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.shared.items.schemas import ChoiceGroupResponse, SourceItemResponse
from app.features.subclasses.crud.schemas import SubclassGetAllResponse


class ClassBase(BaseModel):
    """Base class fields shared by create, update, and response schemas."""

    name: str
    hit_dice: DiceType
    skill_choice_count: int = 2
    spellcasting_ability: AbilityScore | None
    description: str = ""
    image_url: str | None = None


class ClassCreate(ClassBase):
    """
    Create payload for a class: base fields only.

    ``saving_throws``, ``armor_proficiencies``, ``weapon_proficiencies``,
    ``available_skills``, features, subclasses, starting items, and spell
    slots are all deliberately not part of create — each is attached
    afterwards through its own dedicated endpoint.
    """


class ClassUpdate(BaseModel):
    """All fields optional — PATCH semantics. ``saving_throws``, ``armor_proficiencies`` and ``weapon_proficiencies`` are full-replace when set."""

    name: str | None = None
    hit_dice: DiceType | None = None
    skill_choice_count: int | None = None
    spellcasting_ability: AbilityScore | None = None
    description: str | None = None
    saving_throws: list[AbilityScore] | None = None

    @field_validator("saving_throws")
    def validate_unique_saving_throws_update(cls, v):
        """Reject duplicate saving throws when set."""

        if v is None:
            return v

        return _validate_unique_saving_throws(v)


class ClassResponse(ClassBase):
    """
    Full class representation returned by the API.

    Doubles as both the create/update response and the ``GET /classes/{id}``
    response: ``get_by_id`` folds the class's own CLASS-source ``features``
    into it (cached as a single unit), while ``create``/``update`` return it
    with ``features`` at its empty default.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    saving_throws: list[SavingThrowResponse] = []
    armor_proficiencies: list[ArmorProficiencyResponse] = []
    weapon_proficiencies: list[WeaponProficiencyResponse] = []
    available_skills: list[SkillResponse] = []
    starting_items: list[SourceItemResponse] = []
    starting_choice_groups: list[ChoiceGroupResponse] = []
    spell_slot_progression: list[SpellSlotProgressionResponse] = []
    features: list[NestedFeatureResponse] = []
    subclasses: list[SubclassGetAllResponse] = []


class ClassGetAllResponse(BaseModel):
    """Lightweight listing row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    hit_dice: DiceType
    subclasses: list[SubclassGetAllResponse] = []
    image_url: str | None = None
