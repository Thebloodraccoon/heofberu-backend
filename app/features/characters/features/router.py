"""
Character feature endpoint: the read-only feature listing (``/characters``
prefix applied by ``app.features.characters.router``). Writes are GM-only
and live in ``app.features.characters.gm_panel.features``.
"""

from fastapi import APIRouter

from app.features.auth.dependencies import CurrentUserDep
from app.features.characters.dependencies import CharacterFeatureServiceDep
from app.features.characters.features.schemas import CharacterFeatureResponse

router = APIRouter()


@router.get(
    "/{character_id:int}/features",
    response_model=list[CharacterFeatureResponse],
    summary="List a character's features",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_features(
    character_id: int,
    character_feature_service: CharacterFeatureServiceDep,
    current_user: CurrentUserDep,
):
    """List every feature recorded on a character (progression auto-grants plus GM records)."""

    return await character_feature_service.get_features(character_id, current_user)
