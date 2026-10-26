"""Tool endpoints: create a tool, edit its facts."""

from typing import Annotated

from fastapi import APIRouter, Body, status

from app.features.auth.dependencies import GmUserDep
from app.features.items.crud.schemas import ItemResponse
from app.features.items.dependencies import ToolServiceDep
from app.features.items.tools.schemas import ToolCreate, ToolUpdate

router = APIRouter()


@router.post(
    "/tools",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a tool",
    responses={409: {"description": "An item with this name already exists."}},
)
async def create_tool(
    data: Annotated[
        ToolCreate,
        Body(
            openapi_examples={
                "lute": {"summary": "Lute", "value": {"name": "Lute", "tool": {"tool_category": "MUSICAL_INSTRUMENT"}}},
            }
        ),
    ],
    service: ToolServiceDep,
    _: GmUserDep,
):
    """Create a `TOOL` item and its category. **GM only.**"""

    return await service.create(data)


@router.patch(
    "/{item_id:int}/tool",
    response_model=ItemResponse,
    summary="Update a tool's facts",
    responses={
        404: {"description": "No item exists with the given ID."},
        409: {"description": "The item is not a tool."},
    },
)
async def update_tool(item_id: int, data: ToolUpdate, service: ToolServiceDep, _: GmUserDep):
    """Change the tool's category. The core is `PATCH /items/{id}`. **GM only.**"""

    return await service.update_details(item_id, data)
