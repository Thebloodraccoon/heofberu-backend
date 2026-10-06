"""Request/response schemas for a class's spell-slot progression and the derived 1-20 view."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import SpellLevel
from app.features.classes.schema_utils import ensure_unique
from app.features.features.crud.schemas import NestedFeatureResponse

MAX_SPELL_SLOTS = 99


class SpellSlotEntry(BaseModel):
    """One row of a spell slot progression: slots of a given spell level at a given class level."""

    spell_level: SpellLevel
    slots: int = Field(0, ge=0, le=MAX_SPELL_SLOTS)


class SpellSlotProgressionUpdate(BaseModel):
    """Full replacement of the spell slots a class grants at one ``class_level``."""

    slots: list[SpellSlotEntry] = Field(max_length=len(SpellLevel))

    @field_validator("slots")
    def validate_unique_spell_levels(cls, v):
        """Reject duplicate ``spell_level`` entries."""

        ensure_unique([entry.spell_level for entry in v], "spell_level entries")
        return v


class SpellSlotProgressionResponse(BaseModel):
    """Spell slots granted at one class level, as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    class_level: int
    spell_level: SpellLevel
    slots: int


class ProgressionSubclassFeature(NestedFeatureResponse):
    """A subclass feature in the progression table; ``subclass_id`` tells apart the features of different subclasses."""

    subclass_id: int


class ProgressionLevelRow(BaseModel):
    """One row of the class progression table for a given level."""

    level: int
    proficiency_bonus: int

    # ``{spell_level: slots}``; a spell level without a row means 0 slots.
    spell_slots: dict[str, int]

    class_features: list[NestedFeatureResponse]
    subclass_features: list[ProgressionSubclassFeature]


class ClassProgressionResponse(BaseModel):
    """Full 1-20 progression table for a class."""

    class_id: int
    class_name: str
    rows: list[ProgressionLevelRow]
