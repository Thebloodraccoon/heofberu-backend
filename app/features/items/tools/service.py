"""Tool service: a tool's facts."""

from app.constants import ItemKind
from app.features.items.crud.kinds import KindItemService
from app.models.items.item_model import ItemToolDetails


class ToolService(KindItemService):
    """Tools: facts in ``item_tool_details``."""

    kind = ItemKind.TOOL
    detail_attr = "tool"
    detail_model = ItemToolDetails
