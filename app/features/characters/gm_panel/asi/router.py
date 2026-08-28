"""
GM free-form ASI adjustment endpoints: GET/POST/DELETE under ``/gm-panel/asi``
(query-style IDs).

The sub-router declares no prefix of its own; the panel's aggregating
router applies ``/gm-panel``. The character is identified by the
required ``character_id`` query parameter; removal additionally takes
the ``adjustment_id`` query parameter.
"""

from typing import Annotated

from fastapi import APIRouter, Body, Query, status

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
        400: {"description": "The adjustment would push an effective score above the cap of 20."},
        403: {"description": "You are not a GM."},
        404: {"description": "No character exists with the given ID."},
        422: {"description": "Duplicate ability in `increases`."},
    },
)
async def add_character_asi_adjustment(
    character_id: int,
    data: Annotated[
        GmAsiChoiceAdd,
        Body(
            openapi_examples={
                "bump": {
                    "summary": "Grant +1 STR and +2 WIS outside any level budget",
                    "value": {"increases": [{"ability": "STR", "amount": 1}, {"ability": "WIS", "amount": 2}]},
                },
                "lower": {
                    "summary": "Lower CHA as a curse effect",
                    "value": {"increases": [{"ability": "CHA", "amount": -2}]},
                },
            }
        ),
    ],
    asi_service: GmPanelAsiDep,
    current_user: GmUserDep,
):
    """
    Record a free-form ±ability change as an adjustment row in
    `character_asi_choices` (`class_level IS NULL`) — no class level
    required and no +2 budget, but an adjustment may NOT push an
    effective score above the 20 cap. The base columns are never
    touched; the counted increments live in the log and the effective
    totals refresh immediately. **GM only.**
    """

    return await asi_service.add_asi_adjustment(character_id, data, current_user)


@router.delete(
    "/asi",
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
    adjustment_id: Annotated[int, Query(gt=0)],
    asi_service: GmPanelAsiDep,
    current_user: GmUserDep,
):
    """
    Revert one GM ASI adjustment by deleting its log row (the counted
    increments go with it) and refreshing the effective totals. **GM only.**
    """

    await asi_service.remove_asi_adjustment(character_id, adjustment_id, current_user)
    return None
