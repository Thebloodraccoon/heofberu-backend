"""
Character item endpoints: the inventory listing and the sheet's equip toggle
(``/characters`` prefix applied by ``app.features.characters.router``). The
other writes are GM-only and live in ``app.features.characters.gm_panel.items``.
"""

from fastapi import APIRouter

from app.features.auth.dependencies import CurrentUserDep
from app.features.characters.dependencies import CharacterItemServiceDep
from app.features.characters.items.schemas import CharacterItemEquip, CharacterItemResponse

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


@router.patch(
    "/{character_id:int}/items/{stack_id:int}",
    response_model=CharacterItemResponse,
    summary="Equip or unequip an item stack",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No such character, or the stack isn't this character's."},
    },
)
async def set_character_item_equipped(
    character_id: int,
    stack_id: int,
    data: CharacterItemEquip,
    character_item_service: CharacterItemServiceDep,
    current_user: CurrentUserDep,
):
    """
    Put an item on (`is_equipped: true`) or take it off — the player's own toggle on the sheet (owner, campaign
    GM or founder). Equipped armor/shields and active items' effects feed `GET /characters/{id}/combat-stats`.
    """

    return await character_item_service.set_equipped(character_id, stack_id, data, current_user)
