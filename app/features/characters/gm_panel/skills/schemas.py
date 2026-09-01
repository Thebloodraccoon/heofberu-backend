"""Schemas for GM management of a character's skill proficiencies."""

from pydantic import BaseModel, ConfigDict


class SkillExpertiseUpdate(BaseModel):
    """Toggle expertise on one of the character's skill proficiencies."""

    model_config = ConfigDict(extra="forbid")

    is_expertise: bool
