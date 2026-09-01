"""Spell availability schemas: full-replace class/subclass/race/subrace availability payloads."""

from pydantic import BaseModel


class ClassAvailabilityUpdate(BaseModel):
    """Full replacement list of class IDs a spell is available to."""

    class_ids: list[int]


class SubclassAvailabilityUpdate(BaseModel):
    """Full replacement list of subclass IDs a spell is available to."""

    subclass_ids: list[int]


class RaceAvailabilityUpdate(BaseModel):
    """Full replacement list of race IDs a spell is available to."""

    race_ids: list[int]


class SubraceAvailabilityUpdate(BaseModel):
    """Full replacement list of subrace IDs a spell is available to."""

    subrace_ids: list[int]
