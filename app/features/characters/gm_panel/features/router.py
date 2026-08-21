"""
GM feature-grant endpoints: POST/PATCH/DELETE under ``/gm-panel/features``.

The sub-router declares no prefix of its own; the panel's aggregating
router applies ``/{character_id}/gm-panel``.
"""

from fastapi import APIRouter, status

from app.core.security.dependencies import GmUserDep
from app.features.characters.gm_panel.dependencies import GmPanelFeaturesDep
from app.features.characters.gm_panel.features.schemas import CharacterFeatureAdd, CharacterFeatureUpdate
from app.features.characters.schemas import CharacterFeatureResponse

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
    data: CharacterFeatureAdd,
    feature_service: GmPanelFeaturesDep,
    current_user: GmUserDep,
):
    """Record a reference feature on a character. GM-only endpoint."""

    return await feature_service.add_feature(character_id, data, current_user)


@router.patch(
    "/features/{character_feature_id}",
    response_model=CharacterFeatureResponse,
    summary="Change a feature grant's notes",
    responses={
        403: {"description": "You are not a GM."},
        404: {
            "description": "No character exists with the given ID, or no feature grant exists with the given `character_feature_id`."
        },
    },
)
async def update_character_feature(
    character_id: int,
    character_feature_id: int,
    data: CharacterFeatureUpdate,
    feature_service: GmPanelFeaturesDep,
    current_user: GmUserDep,
):
    """Replace the notes on an already-recorded feature. GM-only endpoint."""

    return await feature_service.update_feature(character_id, character_feature_id, data, current_user)


@router.delete(
    "/features/{character_feature_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a feature from a character",
    responses={
        403: {"description": "You are not a GM."},
        404: {
            "description": "No character exists with the given ID, or no feature grant exists with the given `character_feature_id`."
        },
    },
)
async def remove_character_feature(
    character_id: int,
    character_feature_id: int,
    feature_service: GmPanelFeaturesDep,
    current_user: GmUserDep,
):
    """Remove a feature grant from a character. GM-only endpoint."""

    await feature_service.remove_feature(character_id, character_feature_id, current_user)
    return None
