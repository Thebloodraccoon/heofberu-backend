"""
GM stats-overview endpoint: GET under ``/gm-panel/stats``.

The sub-router declares no prefix of its own; the panel's aggregating
router applies ``/{character_id}/gm-panel``.
"""

from fastapi import APIRouter

from app.core.security.dependencies import CurrentUserDep
from app.features.characters.gm_panel.dependencies import GmPanelStatsDep
from app.features.characters.gm_panel.stats.schemas import GmCharacterStatsResponse

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
    character_id: int,
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
