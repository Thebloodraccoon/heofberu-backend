"""Tool write schemas: ``POST /items/tools`` and ``PATCH /items/{id}/tool``."""

from pydantic import BaseModel, ConfigDict

from app.constants import ToolCategory
from app.features.items.crud.schemas import ItemCoreCreate


class ToolDetailsIn(BaseModel):
    """A tool's facts: its category (what an open «any musical instrument» pick filters on)."""

    model_config = ConfigDict(extra="forbid")

    tool_category: ToolCategory | None = None


class ToolCreate(ItemCoreCreate):
    """A new tool: the core and its facts (``tool``)."""

    tool: ToolDetailsIn = ToolDetailsIn()


class ToolUpdate(ToolDetailsIn):
    """PATCH a tool's facts."""
