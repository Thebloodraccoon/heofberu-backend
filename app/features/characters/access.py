"""Character lookup and ownership access-control helpers."""

from app.constants import UserRole
from app.features.characters.crud.repository import CharacterRepository
from app.features.characters.exceptions import CharacterAccessDeniedException, CharacterNotFoundException
from app.features.users.schemas import UserResponse
from app.models.character_model import Character


async def get_character_or_404(repository: CharacterRepository, character_id: int, *, light: bool = False) -> Character:
    """
    Fetch a character by ID, or raise ``CharacterNotFoundException``.
    """

    character = await repository.get_by_id_light(character_id) if light else await repository.get_by_id(character_id)
    if not character:
        raise CharacterNotFoundException(character_id=character_id)

    return character


def check_character_access(character: Character, current_user: UserResponse) -> None:
    """
    Raise ``CharacterAccessDeniedException`` unless the user is GM or the owner.
    """

    if current_user.role in (UserRole.GM, UserRole.FOUND_FATHER):
        return

    if character.owner_id != current_user.id:
        raise CharacterAccessDeniedException()


async def get_character_for_user(
    repository: CharacterRepository,
    character_id: int,
    current_user: UserResponse,
    *,
    light: bool = False,
) -> Character:
    """
    Fetch a character by ID and enforce access control in one call.
    """

    character = await get_character_or_404(repository, character_id, light=light)
    check_character_access(character, current_user)
    return character
