"""Character combat-stats endpoint (``app.features.characters.router`` applies the ``/characters`` prefix)."""

from fastapi import APIRouter

from app.features.auth.dependencies import CurrentUserDep
from app.features.characters.combat.schemas import CharacterCombatStatsResponse
from app.features.characters.dependencies import CharacterCombatServiceDep

router = APIRouter()


@router.get(
    "/{character_id:int}/combat-stats",
    response_model=CharacterCombatStatsResponse,
    summary="Get a character's manual and computed AC and speeds",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_combat_stats(
    character_id: int, combat_service: CharacterCombatServiceDep, current_user: CurrentUserDep
):
    """
    AC and speeds twice: `manual` — the sheet's own `armor_class`/`shield`/`speed` the player edits — and
    `computed` from the equipped armor/shield, DEX, feature effects (Unarmored Defense, Fast Movement...)
    and equipped items' effects, each with a `breakdown` of where every number comes from.
    """

    return await combat_service.get_combat_stats(character_id, current_user)
