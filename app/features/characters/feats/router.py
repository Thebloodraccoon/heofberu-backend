"""
Character feat endpoint: the read-only feat listing (``/characters``
prefix applied by ``app.features.characters.router``). Writes are GM-only
and live in ``app.features.characters.gm_panel.feats``.
"""

from fastapi import APIRouter

from app.features.auth.dependencies import CurrentUserDep
from app.features.characters.dependencies import CharacterFeatServiceDep
from app.features.characters.feats.schemas import CharacterFeatResponse

router = APIRouter()


@router.get(
    "/{character_id:int}/feats",
    response_model=list[CharacterFeatResponse],
    summary="List a character's feats",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_feats(
    character_id: int,
    character_feat_service: CharacterFeatServiceDep,
    current_user: CurrentUserDep,
):
    """List every feat granted to a character (level-up choices and GM grants alike)."""

    return await character_feat_service.get_feats(character_id, current_user)
