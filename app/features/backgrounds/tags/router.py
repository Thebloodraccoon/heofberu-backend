"""Background tag endpoints (mounted under ``/backgrounds/{background_id}``)."""

from typing import Annotated

from fastapi import APIRouter, Body

from app.features.auth.dependencies import GmUserDep
from app.features.backgrounds.crud.schemas import BackgroundResponse
from app.features.backgrounds.dependencies import BackgroundTagsDep
from app.features.shared.tags.schemas import TagsUpdate

router = APIRouter()


@router.put(
    "/tags",
    response_model=BackgroundResponse,
    summary="Replace a background's tags",
    responses={
        400: {"description": "One or more tag IDs don't correspond to an existing tag."},
        404: {"description": "No background exists with the given ID."},
    },
)
async def set_background_tags(
    background_id: int,
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
    background_service: BackgroundTagsDep,
    _: GmUserDep,
):
    """Replace all tags for a background, from the shared tag dictionary. **GM only.**"""

    return await background_service.set_tags(background_id, data)
