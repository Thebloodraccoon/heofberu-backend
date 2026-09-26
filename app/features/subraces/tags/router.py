"""Subrace tag endpoints: full replacement of a subrace's tags."""

from typing import Annotated

from fastapi import APIRouter, Body

from app.features.shared.tags.schemas import TagsUpdate
from app.features.subraces.crud.schemas import SubraceResponse
from app.features.subraces.dependencies import SubraceTagsDep
from app.features.users.security import GmUserDep

router = APIRouter()


@router.put(
    "/{subrace_id:int}/tags",
    response_model=SubraceResponse,
    summary="Replace a subrace's tags",
    responses={
        400: {"description": "One or more tag IDs don't correspond to an existing tag."},
        404: {"description": "No subrace exists with the given ID."},
    },
)
async def set_tags(
    subrace_id: int,
    data: Annotated[
        TagsUpdate,
        Body(
            openapi_examples={
                "replace": {
                    "summary": "Replace with two tags",
                    "value": {"tag_ids": [3, 7]},
                },
                "clear": {
                    "summary": "Clear all tags",
                    "value": {"tag_ids": []},
                },
            },
        ),
    ],
    subrace_service: SubraceTagsDep,
    _: GmUserDep,
):
    """Replace all tags for a subrace, from the shared tag dictionary. **GM only.**"""

    return await subrace_service.set_tags(subrace_id, data)
