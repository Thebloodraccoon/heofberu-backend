"""
GM free-form ASI adjustment endpoints: GET/POST/DELETE under ``/gm-panel/asi``.

The sub-router declares no prefix of its own; the panel's aggregating
router applies ``/{character_id}/gm-panel``.
"""

from fastapi import APIRouter, status

from app.features.characters.gm_panel.asi.schemas import GmAsiChoiceAdd, GmAsiChoiceResponse
from app.features.characters.gm_panel.dependencies import GmPanelAsiDep
from app.features.users.security import CurrentUserDep, GmUserDep

router = APIRouter()


@router.get(
    "/asi",
    response_model=list[GmAsiChoiceResponse],
    summary="List a character's GM ASI adjustments",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_asi_adjustments(
    character_id: int,
    asi_service: GmPanelAsiDep,
    current_user: CurrentUserDep,
):
    """List every free-form GM ASI adjustment (level-tied choices excluded)."""

    return await asi_service.get_asi_adjustments(character_id, current_user)


@router.post(
    "/asi",
    response_model=GmAsiChoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a GM ASI adjustment (independent of level)",
    responses={
        403: {"description": "You are not a GM."},
        404: {"description": "No character exists with the given ID."},
        422: {"description": "Duplicate ability in `increases`."},
    },
)
async def add_character_asi_adjustment(
    character_id: int,
    data: GmAsiChoiceAdd,
    asi_service: GmPanelAsiDep,
    current_user: GmUserDep,
):
    """

    Apply a free-form ±ability change to the character's base scores —
    no class level required and no 20 cap or +2 budget enforced.

    The bumps commit together with an audit row in
    `character_asi_choices` (`class_level IS NULL`), and the effective
    ability-score totals are refreshed. GM-only endpoint.
    """

    return await asi_service.add_asi_adjustment(character_id, data, current_user)


@router.delete(
    "/asi/{adjustment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revert a GM ASI adjustment",
    responses={
        400: {"description": "The choice is tied to a class level (managed by level-ups, not the panel)."},
        403: {"description": "You are not a GM."},
        404: {"description": "No character or GM ASI adjustment exists with the given ID."},
    },
)
async def remove_character_asi_adjustment(
    character_id: int,
    adjustment_id: int,
    asi_service: GmPanelAsiDep,
    current_user: GmUserDep,
):
    """
    Revert one GM ASI adjustment: subtract its recorded increases from
    the base scores and delete the audit row. GM-only endpoint.
    """

    await asi_service.remove_asi_adjustment(character_id, adjustment_id, current_user)
    return None
