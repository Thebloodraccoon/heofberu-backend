"""Public character endpoints: the owner's visibility switch and the anonymous public card."""

from fastapi import APIRouter

from app.features.auth.dependencies import CurrentUserDep
from app.features.characters.dependencies import CharacterVisibilityServiceDep
from app.features.characters.visibility.schemas import (
    CharacterVisibilityResponse,
    CharacterVisibilityUpdate,
    PublicCharacterCard,
)

router = APIRouter()


@router.patch(
    "/{character_id:int}/public-visibility",
    response_model=CharacterVisibilityResponse,
    summary="Set how much of a character is shown publicly",
    responses={
        403: {"description": "Only the character's owner can change it (not the GM, not the founder)."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def set_public_visibility(
    character_id: int,
    data: CharacterVisibilityUpdate,
    service: CharacterVisibilityServiceDep,
    current_user: CurrentUserDep,
):
    """
    `hidden` (default): nowhere public. `full`: name, level, race/subrace, class/subclass and background ids,
    personality, backstory (write secrets for your GM inside `:::gm` ... `:::` blocks — they are never shown), base
    and total ability scores, skill and saving-throw proficiencies. Inventory and spells are never shown.
    Applies at once everywhere, including public campaign showcases. **Owner only.**
    """

    return await service.set_visibility(character_id, data, current_user)


@router.get(
    "/{character_id:int}/public",
    response_model=PublicCharacterCard,
    response_model_exclude_none=True,
    summary="Get a character's public card",
    responses={404: {"description": "No such character, or its owner keeps it hidden."}},
)
async def get_public_card(character_id: int, service: CharacterVisibilityServiceDep):
    """The character as its owner chose to show it. Campaign data is never part of it. Open endpoint."""

    return await service.get_public_card(character_id)
