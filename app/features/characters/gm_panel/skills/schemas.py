"""Schemas for GM management of a character's skill proficiencies."""

from pydantic import BaseModel, ConfigDict


class SkillExpertiseUpdate(BaseModel):
    """
    Toggle expertise on one of the character's skill proficiencies.

    Only ``is_expertise`` is editable, and only on an existing proficiency
    row — proficiency rows themselves are written once at creation (class
    choices plus background/race grants) and are never added or removed
    here. The server stores the flag; clients derive the doubled bonus
    from it.
    """

    model_config = ConfigDict(extra="forbid")

    is_expertise: bool
