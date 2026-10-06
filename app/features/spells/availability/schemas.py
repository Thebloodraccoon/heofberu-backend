"""Spell availability schemas: full-replace class/subclass/race/subrace availability payloads."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.features.spells.crud.schemas import AvailabilityIds, dedupe_ids


class _AvailabilityUpdate(BaseModel):
    """Shared rules: unknown keys rejected, ids bounded and de-duplicated (order kept)."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def dedupe(cls, value):
        """Repeated ids collapse to one."""

        return dedupe_ids(value)


class ClassAvailabilityUpdate(_AvailabilityUpdate):
    """Full replacement list of class IDs a spell is available to."""

    class_ids: AvailabilityIds


class SubclassAvailabilityUpdate(_AvailabilityUpdate):
    """Full replacement list of subclass IDs a spell is available to."""

    subclass_ids: AvailabilityIds


class RaceAvailabilityUpdate(_AvailabilityUpdate):
    """Full replacement list of race IDs a spell is available to."""

    race_ids: AvailabilityIds


class SubraceAvailabilityUpdate(_AvailabilityUpdate):
    """Full replacement list of subrace IDs a spell is available to."""

    subrace_ids: AvailabilityIds
