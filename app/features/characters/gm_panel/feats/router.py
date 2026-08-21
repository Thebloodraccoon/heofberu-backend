"""
GM feat-grant endpoints: POST/PATCH/DELETE under ``/gm-panel/feats``.

The sub-router declares no prefix of its own; the panel's aggregating
router applies ``/{character_id}/gm-panel``.
"""

from fastapi import APIRouter, status

from app.core.security.dependencies import GmUserDep
from app.features.characters.gm_panel.dependencies import GmPanelFeatsDep
from app.features.characters.gm_panel.feats.schemas import CharacterFeatAdd, CharacterFeatUpdate
from app.features.characters.schemas import CharacterFeatResponse

router = APIRouter()


@router.post(
    "/feats",
    response_model=CharacterFeatResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Grant a feat to a character",
    responses={
        400: {
            "description": (
                "`ability_score_increase_id` doesn't belong to this feat, or the "
                "character doesn't meet the feat's ability-score prerequisite."
            )
        },
        403: {"description": "You are not a GM."},
        404: {"description": "No character or feat exists with the given ID."},
        409: {"description": "The character already has this feat."},
    },
)
async def add_character_feat(
    character_id: int,
    data: CharacterFeatAdd,
    feat_service: GmPanelFeatsDep,
    current_user: GmUserDep,
):
    """Grant a feat to a character. GM-only endpoint."""

    return await feat_service.add_feat(character_id, data, current_user)


@router.patch(
    "/feats/{character_feat_id}",
    response_model=CharacterFeatResponse,
    summary="Change a feat grant's ability score increase choice",
    responses={
        400: {"description": "`ability_score_increase_id` doesn't belong to this feat."},
        403: {"description": "You are not a GM."},
        404: {
            "description": "No character exists with the given ID, or no feat grant exists with the given `character_feat_id`."
        },
    },
)
async def update_character_feat(
    character_id: int,
    character_feat_id: int,
    data: CharacterFeatUpdate,
    feat_service: GmPanelFeatsDep,
    current_user: GmUserDep,
):
    """Change or clear the ASI choice for an already-granted feat. GM-only endpoint."""

    return await feat_service.update_feat(character_id, character_feat_id, data, current_user)


@router.delete(
    "/feats/{character_feat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a feat from a character",
    responses={
        403: {"description": "You are not a GM."},
        404: {
            "description": "No character exists with the given ID, or no feat grant exists with the given `character_feat_id`."
        },
    },
)
async def remove_character_feat(
    character_id: int,
    character_feat_id: int,
    feat_service: GmPanelFeatsDep,
    current_user: GmUserDep,
):
    """Revoke a feat from a character. GM-only endpoint."""

    await feat_service.remove_feat(character_id, character_feat_id, current_user)
    return None
