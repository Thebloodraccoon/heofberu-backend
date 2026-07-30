from app.features.characters.exceptions import CharacterAccessDeniedException, CharacterNotFoundException
from app.features.characters.repositories.character_repository import CharacterRepository
from app.features.users.schemas import UserResponse
from app.models.character_model import Character


def get_character_or_404(repository: CharacterRepository, character_id: int) -> Character:
    """Fetch a character by ID, or raise ``CharacterNotFoundException``."""

    character = repository.get_by_id(character_id)
    if not character:
        raise CharacterNotFoundException(character_id=character_id)

    return character


def check_character_access(character: Character, current_user: UserResponse) -> None:
    """
    Raise ``CharacterAccessDeniedException`` unless the user is GM or the owner.

    GM can access any character. Players can only access their own.
    """

    if current_user.role == "gm":
        return

    if character.owner_id != current_user.id:
        raise CharacterAccessDeniedException()


def get_character_for_user(repository: CharacterRepository, character_id: int, current_user: UserResponse) -> Character:
    """
    Fetch a character by ID and enforce access control in one call.

    Combines :func:`get_character_or_404` and :func:`check_character_access`,
    since almost every character-related operation needs both.
    """

    character = get_character_or_404(repository, character_id)
    check_character_access(character, current_user)
    return character
