"""
GM max-HP endpoint: PATCH under ``/gm-panel/max-hp``.

The sub-router declares no prefix of its own; the panel's aggregating
router applies ``/{character_id}/gm-panel``.
"""

from fastapi import APIRouter

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
    data: MaxHpUpdate,
    hp_service: GmPanelHpDep,
    current_user: GmUserDep,
):
    """
    Set a character's `max_hp` directly. GM-only endpoint.

    `max_hp` is intentionally not PATCHable through the plain character
    update — only a GM may change it. When the new maximum is below the
    current HP pool, `current_hp` is clamped down to it; temp HP is
    untouched.
    """

    return await hp_service.set_max_hp(character_id, data, current_user)
