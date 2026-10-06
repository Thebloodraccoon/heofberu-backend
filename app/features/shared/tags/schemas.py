"""
Shared request/response schemas for the tags attached to a catalog record.

One dictionary (``Tag``, see ``app/models/tag_model.py``) backs every catalog's
tags — races, subraces, backgrounds, articles. These schemas are shared
(not duplicated per catalog, unlike ``SkillResponse``) since the tag shape
itself never varies by owner.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.types import EntityId

MAX_TAG_IDS = 100


def _validate_unique_tag_ids(tag_ids: list[int]) -> list[int]:
    """Reject lists containing duplicate tag IDs."""

    if len(tag_ids) != len(set(tag_ids)):
        raise ValueError("Duplicate tag IDs are not allowed.")

    return tag_ids


class TagsUpdate(BaseModel):
    """Full replacement list of tag IDs attached to a catalog record."""

    tag_ids: list[EntityId] = Field(max_length=MAX_TAG_IDS)

    @field_validator("tag_ids")
    def validate_unique_tag_ids(cls, tag_ids):
        """Reject lists containing duplicate tag IDs."""

        return _validate_unique_tag_ids(tag_ids)


class TagBrief(BaseModel):
    """Brief tag representation embedded in catalog responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
