"""GM feature-grant endpoints: POST/DELETE under ``/gm-panel/features`` (query-style IDs)."""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.features.characters.features.schemas import CharacterFeatureResponse
from app.features.characters.gm_panel.dependencies import GmPanelFeaturesDep
from app.features.characters.gm_panel.features.schemas import CharacterFeatureAdd
from app.features.users.security import GmUserDep

router = APIRouter()


@router.post(
    "/features",
    response_model=CharacterFeatureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a feature on a character",
    responses={
        403: {"description": "You are not a GM."},
        404: {"description": "No character or feature exists with the given ID."},
        409: {"description": "The character already has this feature."},
    },
)
async def add_character_feature(
    character_id: int,
    data: Annotated[
        CharacterFeatureAdd,
        Body(
            openapi_examples={
                "add": {
                    "summary": "Record a feature",
                    "value": {"feature_id": 21},
                },
            }
        ),
    ],
    feature_service: GmPanelFeaturesDep,
    current_user: GmUserDep,
):
    """
    Record a reference feature on a character outside the automatic
    progression grants. **GM only.**
    """

    return await feature_service.add_feature(character_id, data, current_user)


@router.delete(
    "/features",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a feature from a character",
    responses={
        403: {"description": "You are not a GM."},
        404: {
            "description": "No character exists with the given ID, or no feature grant exists with the given `feature_id`."
        },
    },
)
async def remove_character_feature(
    character_id: int,
    feature_id: Annotated[int, Query(gt=0)],
    feature_service: GmPanelFeaturesDep,
    current_user: GmUserDep,
):
    """
    Remove a feature grant from a character, deleting the grant row
    (progression auto-grants can be removed here too). **GM only.**
    """

    await feature_service.remove_feature(character_id, feature_id, current_user)
    return None
