"""Spell availability schemas: full-replace class/race availability payloads."""

from pydantic import BaseModel


class ClassAvailabilityUpdate(BaseModel):
    """Full replacement list of class IDs a spell is available to. Empty = unrestricted."""

    class_ids: list[int]


class RaceAvailabilityUpdate(BaseModel):
    """Full replacement list of race IDs a spell is available to. Empty = unrestricted."""

    race_ids: list[int]
