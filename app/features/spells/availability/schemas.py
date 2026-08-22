"""Spell availability schemas: full-replace class/subclass/race/subrace availability payloads."""

from pydantic import BaseModel


class ClassAvailabilityUpdate(BaseModel):
    """Full replacement list of class IDs a spell is available to. Empty = unrestricted."""

    class_ids: list[int]


class SubclassAvailabilityUpdate(BaseModel):
    """Full replacement list of subclass IDs a spell is available to. Empty = unrestricted."""

    subclass_ids: list[int]


class RaceAvailabilityUpdate(BaseModel):
    """Full replacement list of race IDs a spell is available to. Empty = unrestricted."""

    race_ids: list[int]


class SubraceAvailabilityUpdate(BaseModel):
    """Full replacement list of subrace IDs a spell is available to. Empty = unrestricted."""

    subrace_ids: list[int]
