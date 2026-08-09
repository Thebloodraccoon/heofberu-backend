"""Character lookup and ownership access-control helpers."""

from app.constants import UserRole
from app.features.characters.core.repository import CharacterRepository
from app.features.characters.exceptions import CharacterAccessDeniedException, CharacterNotFoundException
from app.features.users.schemas import UserResponse
from app.models.character_model import Character


async def get_character_or_404(repository: CharacterRepository, character_id: int, *, light: bool = False) -> Character:
    """
    Fetch a character by ID, or raise ``CharacterNotFoundException``.

    ``light=True`` skips the eager-loaded collections
    (``get_by_id_light``) — for callers that only need the scalar
    columns (sub-domain access checks and writes).
    """

    character = await repository.get_by_id_light(character_id) if light else await repository.get_by_id(character_id)
    if not character:
        raise CharacterNotFoundException(character_id=character_id)

    return character


def check_character_access(character: Character, current_user: UserResponse) -> None:
    """
    Raise ``CharacterAccessDeniedException`` unless the user is GM or the owner.

    GM can access any character. Players can only access their own.
    """

    if current_user.role == UserRole.GM:
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

    Combines :func:`get_character_or_404` and :func:`check_character_access`,
    since almost every character-related operation needs both.
    ``light=True`` skips the eager-loaded collections — for sub-domain
    paths that only read scalar columns.
    """

    character = await get_character_or_404(repository, character_id, light=light)
    check_character_access(character, current_user)
    return character
