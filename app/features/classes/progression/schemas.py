"""Request/response schemas for a class's spell-slot progression and the derived 1-20 view."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.constants import SpellLevel
from app.features.features.crud.schemas import NestedFeatureResponse


def _validate_unique_spell_levels(slots: list["SpellSlotEntry"]) -> list["SpellSlotEntry"]:
    """Reject duplicate ``spell_level`` entries."""

    levels = [entry.spell_level for entry in slots]
    if len(levels) != len(set(levels)):
        raise ValueError("Duplicate spell_level entries are not allowed.")

    return slots


class SpellSlotEntry(BaseModel):
    """One row of a spell slot progression: slots of a given spell level at a given class level."""

    spell_level: SpellLevel
    slots: int = 0


class SpellSlotProgressionUpdate(BaseModel):
    """Full replacement of the spell slots a class grants at one ``class_level``."""

    slots: list[SpellSlotEntry]

    @field_validator("slots")
    def validate_unique_spell_levels(cls, v):
        """Reject duplicate ``spell_level`` entries."""

        return _validate_unique_spell_levels(v)


class SpellSlotProgressionResponse(BaseModel):
    """Spell slots granted at one class level, as returned in responses."""

    model_config = ConfigDict(from_attributes=True)

    class_level: int
    spell_level: SpellLevel
    slots: int


class ProgressionLevelRow(BaseModel):
    """One row of the class progression table for a given level."""

    level: int
    proficiency_bonus: int

    # spell slots: {spell_level → slots}, only levels with rows are included.
    # e.g. {"LEVEL_1": 4, "LEVEL_2": 2}  — absent means 0 slots.
    spell_slots: dict[str, int]

    # CLASS-source features gained at this level.
    class_features: list[NestedFeatureResponse]

    # SUBCLASS features grouped by subclass name, gained at this level.
    # Only populated for levels where at least one subclass grants a feature.
    subclass_features: list[NestedFeatureResponse]


class ClassProgressionResponse(BaseModel):
    """Full 1-20 progression table for a class."""

    class_id: int
    class_name: str
    rows: list[ProgressionLevelRow]
