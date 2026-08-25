"""
GM stats-overview endpoint: GET under ``/gm-panel/stats`` (query-style ID).

The sub-router declares no prefix of its own; the panel's aggregating
router applies ``/gm-panel``. The character is identified by the
required ``character_id`` query parameter.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.features.characters.gm_panel.dependencies import GmPanelStatsDep
from app.features.characters.gm_panel.stats.schemas import GmCharacterStatsResponse
from app.features.users.security import CurrentUserDep

router = APIRouter()


@router.get(
    "/stats",
    response_model=GmCharacterStatsResponse,
    summary="Original vs computed ability scores",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_stats(
    character_id: Annotated[int, Query(gt=0)],
    stats_service: GmPanelStatsDep,
    current_user: CurrentUserDep,
):
    """
    Return each of the six abilities as `{base, total}`: the ORIGINAL
    base value (player entry plus level-up/GM bumps) next to its COMPUTED
    effective total (base + race/subrace/feat bonuses), freshly
    calculated — never read from the possibly-stale cache.
    """

    return await stats_service.get_stats(character_id, current_user)
