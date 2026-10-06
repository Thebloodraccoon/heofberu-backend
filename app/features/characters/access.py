"""Character lookup and ownership access-control helpers."""

from app.constants import UserRole
from app.features.characters.crud.repository import CharacterRepository
from app.features.characters.exceptions import CharacterAccessDeniedException, CharacterNotFoundException
from app.features.users.schemas import UserResponse
from app.models.character.character_model import Character

GM_ROLES = (UserRole.GM, UserRole.FOUND_FATHER)


def is_gm(user: UserResponse) -> bool:
    """Whether ``user`` has GM-level access (GM or founder)."""

    return user.role in GM_ROLES


async def get_character_or_404(repository: CharacterRepository, character_id: int, *, light: bool = False) -> Character:
    """
    Fetch a character by ID, or raise ``CharacterNotFoundException``.

    ``light=True`` skips ``populate_existing``: an instance already in the
    session identity map is returned as-is instead of being re-read.
    """

    character = await repository.get_by_id_light(character_id) if light else await repository.get_by_id(character_id)
    if not character:
        raise CharacterNotFoundException(character_id=character_id)

    return character


def check_owner_access(owner_id: int, current_user: UserResponse) -> None:
    """Raise ``CharacterAccessDeniedException`` unless the user is a GM or ``owner_id``."""

    if not is_gm(current_user) and owner_id != current_user.id:
        raise CharacterAccessDeniedException()


def check_character_access(character: Character, current_user: UserResponse) -> None:
    """Raise ``CharacterAccessDeniedException`` unless the user is GM or the owner."""

    check_owner_access(character.owner_id, current_user)


async def get_character_for_user(
    repository: CharacterRepository,
    character_id: int,
    current_user: UserResponse,
    *,
    light: bool = False,
) -> Character:
    """Fetch a character by ID and enforce access control in one call."""

    character = await get_character_or_404(repository, character_id, light=light)
    check_character_access(character, current_user)
    return character


async def ensure_character_access(
    repository: CharacterRepository, character_id: int, current_user: UserResponse
) -> None:
    """
    Enforce GM/owner access without loading the character row: one
    ``owner_id`` lookup. For sub-resource endpoints that never read the
    character itself.
    """

    owner_id = await repository.get_owner_id(character_id)
    if owner_id is None:
        raise CharacterNotFoundException(character_id=character_id)

    check_owner_access(owner_id, current_user)
