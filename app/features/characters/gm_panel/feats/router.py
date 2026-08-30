"""
GM feat-grant endpoints: POST/PATCH/DELETE under ``/gm-panel/feats``
(query-style IDs).

The sub-router declares no prefix of its own; the panel's aggregating
router applies ``/gm-panel``. The character is identified by the
required ``character_id`` query parameter; grant edits/removals
additionally take ``feat_id`` (the character-feat grant row ID).
"""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

from app.features.characters.gm_panel.dependencies import GmPanelFeatsDep
from app.features.characters.gm_panel.feats.schemas import CharacterFeatAdd, CharacterFeatUpdate
from app.features.characters.schemas import CharacterFeatResponse
from app.features.users.security import GmUserDep

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
        422: {
            "description": (
                "The feat offers ability-score increase options but no "
                "`ability_score_increase_id` was chosen — the choice is required."
            )
        },
    },
)
async def add_character_feat(
    character_id: int,
    data: Annotated[
        CharacterFeatAdd,
        Body(
            openapi_examples={
                "plain-feat": {
                    "summary": "Grant a feat with no ASI choice",
                    "value": {"feat_id": 12},
                },
                "feat-with-asi": {
                    "summary": "Grant Resilient, applying its +1 CON increase",
                    "value": {"feat_id": 12, "ability_score_increase_id": 34},
                },
            }
        ),
    ],
    feat_service: GmPanelFeatsDep,
    current_user: GmUserDep,
):
    """
    Grant a feat to a character outside any level-up flow. If the feat
    offers ability-score increase options, a matching
    ``ability_score_increase_id`` MUST be chosen (422 otherwise); each
    granted point is also recorded in the character's ASI-choice log.
    **GM only.**
    """

    return await feat_service.add_feat(character_id, data, current_user)


@router.patch(
    "/feats",
    response_model=CharacterFeatResponse,
    summary="Change a feat grant's ability score increase choice",
    responses={
        400: {"description": "`ability_score_increase_id` doesn't belong to this feat."},
        403: {"description": "You are not a GM."},
        404: {
            "description": "No character exists with the given ID, or no feat grant exists with the given `feat_id`."
        },
        422: {
            "description": (
                "The feat offers ability-score increase options but no "
                "`ability_score_increase_id` was provided — clearing is not allowed."
            )
        },
    },
)
async def update_character_feat(
    character_id: int,
    feat_id: Annotated[int, Query(gt=0)],
    data: Annotated[
        CharacterFeatUpdate,
        Body(
            openapi_examples={
                "update": {
                    "summary": "Point the feat's ASI choice at another increase row",
                    "value": {"ability_score_increase_id": 35},
                },
            }
        ),
    ],
    feat_service: GmPanelFeatsDep,
    current_user: GmUserDep,
):
    """
    Change the ability-score increase chosen for an already-granted feat
    (a feat offering ASI options must always keep one). **GM only.**
    """

    return await feat_service.update_feat(character_id, feat_id, data, current_user)


@router.delete(
    "/feats",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a feat from a character",
    responses={
        403: {"description": "You are not a GM."},
        404: {
            "description": "No character exists with the given ID, or no feat grant exists with the given `feat_id`."
        },
    },
)
async def remove_character_feat(
    character_id: int,
    feat_id: Annotated[int, Query(gt=0)],
    feat_service: GmPanelFeatsDep,
    current_user: GmUserDep,
):
    """
    Revoke a feat from a character, removing the grant row and any
    ability-score increase it applied. **GM only.**
    """

    await feat_service.remove_feat(character_id, feat_id, current_user)
    return None
