"""
GM max-HP endpoint: PATCH under ``/gm-panel/max-hp`` (query-style ID).

The sub-router declares no prefix of its own; the panel's aggregating
router applies ``/gm-panel``. The character is identified by the
required ``character_id`` query parameter.
"""

from typing import Annotated

from fastapi import APIRouter, Body, Query

from app.features.characters.gm_panel.dependencies import GmPanelHpDep
from app.features.characters.gm_panel.hp.schemas import MaxHpUpdate
from app.features.characters.schemas import CharacterResponse
from app.features.users.security import GmUserDep

router = APIRouter()


@router.patch(
    "/max-hp",
    response_model=CharacterResponse,
    summary="Set a character's maximum HP",
    responses={
        403: {"description": "You are not a GM."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def set_character_max_hp(
    character_id: int,
    data: Annotated[
        MaxHpUpdate,
        Body(
            openapi_examples={
                "set": {
                    "summary": "Set the maximum HP to 24 (e.g. after a tough homebrew boon)",
                    "value": {"max_hp": 24},
                },
            }
        ),
    ],
    hp_service: GmPanelHpDep,
    current_user: GmUserDep,
):
    """
    Set a character's `max_hp` directly. `max_hp` is intentionally not
    PATCHable through the plain character update — only a GM may change
    it. When the new maximum is below the current HP pool, `current_hp`
    is clamped down to it; temp HP is untouched. **GM only.**
    """

    return await hp_service.set_max_hp(character_id, data, current_user)
