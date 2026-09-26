"""Race tag endpoints: full replacement of a race's tags."""

from typing import Annotated

from fastapi import APIRouter, Body

from app.features.races.crud.schemas import RaceResponse
from app.features.races.dependencies import RaceTagsDep
from app.features.shared.tags.schemas import TagsUpdate
from app.features.users.security import GmUserDep

router = APIRouter()


@router.put(
    "/{race_id:int}/tags",
    response_model=RaceResponse,
    summary="Replace a race's tags",
    responses={
        400: {"description": "One or more tag IDs don't correspond to an existing tag."},
        404: {"description": "No race exists with the given ID."},
    },
)
async def set_tags(
    race_id: int,
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
    race_service: RaceTagsDep,
    _: GmUserDep,
):
    """Replace all tags for a race, from the shared tag dictionary. **GM only.**"""

    return await race_service.set_tags(race_id, data)
