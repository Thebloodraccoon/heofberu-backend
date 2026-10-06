"""Request/response schemas for the class CRUD endpoints (class identity; capability schemas live in their own folders)."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import AbilityScore, DiceType
from app.features.classes.proficiencies.schemas import (
    ArmorProficiencyResponse,
    SavingThrowResponse,
    WeaponProficiencyResponse,
)
from app.features.classes.progression.schemas import SpellSlotProgressionResponse
from app.features.classes.schema_utils import (
    DESCRIPTION_MAX_LENGTH,
    IMAGE_URL_MAX_LENGTH,
    NAME_MAX_LENGTH,
    ensure_unique,
    null_guard,
    validate_image_url,
)
from app.features.classes.skills.schemas import SkillResponse
from app.features.features.crud.schemas import NestedFeatureResponse
from app.features.shared.items.schemas import ChoiceGroupResponse, SourceItemResponse
from app.features.subclasses.crud.schemas import SubclassGetAllResponse

SKILL_CHOICE_COUNT_MAX = 20


class ClassBase(BaseModel):
    """Base class fields shared by create and response schemas."""

    name: str
    hit_dice: DiceType
    skill_choice_count: int = 2
    spellcasting_ability: AbilityScore | None
    description: str = ""
    image_url: str | None = None


class ClassCreate(ClassBase):
    """
    Create payload for a class: base fields only.

    Saving throws, armor/weapon proficiencies, available skills, features,
    subclasses, starting items and spell slots are attached afterwards through
    their own endpoints.
    """

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    skill_choice_count: int = Field(2, ge=0, le=SKILL_CHOICE_COUNT_MAX)
    description: str = Field("", max_length=DESCRIPTION_MAX_LENGTH)
    image_url: str | None = Field(None, max_length=IMAGE_URL_MAX_LENGTH)

    _image_url = field_validator("image_url")(validate_image_url)


class ClassUpdate(BaseModel):
    """All fields optional (PATCH). ``null`` is only accepted for ``spellcasting_ability`` (clears it) and ``saving_throws`` (leaves them unchanged); ``saving_throws`` is a full replace when set."""

    name: str | None = Field(None, min_length=1, max_length=NAME_MAX_LENGTH)
    hit_dice: DiceType | None = None
    skill_choice_count: int | None = Field(None, ge=0, le=SKILL_CHOICE_COUNT_MAX)
    spellcasting_ability: AbilityScore | None = None
    description: str | None = Field(None, max_length=DESCRIPTION_MAX_LENGTH)
    saving_throws: list[AbilityScore] | None = None

    _no_nulls = null_guard(nullable=frozenset({"spellcasting_ability", "saving_throws"}))

    @field_validator("saving_throws")
    def validate_unique_saving_throws(cls, v):
        """Reject duplicate saving throws when set."""

        return v if v is None else ensure_unique(v, "saving throws")


class ClassResponse(ClassBase):
    """
    Full class representation returned by the API (``GET``, ``POST``, ``PATCH``
    and every ``PUT`` sub-resource write): base fields, child rows, CLASS-source
    ``features`` and a brief reference to every subclass.
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
