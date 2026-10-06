"""
Character item endpoint: the read-only inventory listing (``/characters``
prefix applied by ``app.features.characters.router``). Writes are GM-only
and live in ``app.features.characters.gm_panel.items``.
"""

from fastapi import APIRouter

from app.features.auth.dependencies import CurrentUserDep
from app.features.characters.dependencies import CharacterItemServiceDep
from app.features.characters.items.schemas import CharacterItemResponse

router = APIRouter()


@router.get(
    "/{character_id:int}/items",
    response_model=list[CharacterItemResponse],
    summary="List a character's items",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_items(
    character_id: int,
    character_item_service: CharacterItemServiceDep,
    current_user: CurrentUserDep,
):
    """List every item stack owned by a character (GM/owner readable)."""

    return await character_item_service.get_items(character_id, current_user)
