"""
Character proficiency endpoint: the materialized skill/saving-throw/armor/
weapon surface with grant provenance (``app.features.characters.router``
applies the ``/characters`` prefix).
"""

from fastapi import APIRouter

from app.features.characters.dependencies import CharacterProficiencyServiceDep
from app.features.characters.proficiencies.schemas import CharacterProficienciesResponse
from app.features.users.security import CurrentUserDep

router = APIRouter()


@router.get(
    "/{character_id:int}/proficiencies",
    response_model=CharacterProficienciesResponse,
    summary="List a character's proficiencies with their source",
    responses={
        403: {"description": "You do not have access to this character."},
        404: {"description": "No character exists with the given ID."},
    },
)
async def get_character_proficiencies(
    character_id: int,
    proficiency_service: CharacterProficiencyServiceDep,
    current_user: CurrentUserDep,
):
    """
    List every materialized skill/saving-throw/armor/weapon proficiency,
    each tagged with the feature grant (class/subclass/race/background/
    feat, GM, or ASI) or free-form row it came from.
    """

    return await proficiency_service.get_proficiencies(character_id, current_user)
