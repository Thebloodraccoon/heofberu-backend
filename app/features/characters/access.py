"""
Character lookup and access-control helpers.

Who may read and change a character sheet: its owner, the founder, and the GM of the campaign the character is
currently ``ACTIVE`` in. Holding the global GM role alone grants nothing (a GM owns only their own campaigns).
The campaign check is one query on ``campaign_characters`` (``CharacterRepository.is_managed_by``), made only
for a GM-role caller who is not the owner, so owners and players never pay for it.
"""

from app.constants import UserRole
from app.features.characters.crud.repository import CharacterRepository
from app.features.characters.exceptions import CharacterAccessDeniedException, CharacterNotFoundException
from app.features.users.schemas import UserResponse
from app.models.character.character_model import Character

GM_ROLES = (UserRole.GM, UserRole.FOUND_FATHER)


def is_gm(user: UserResponse) -> bool:
    """Whether ``user`` has a GM-level global role (GM or founder). Not an access grant on its own."""

    return user.role in GM_ROLES


def is_founder(user: UserResponse) -> bool:
    """Whether ``user`` is the founder (bypasses every character check)."""

    return user.role == UserRole.FOUND_FATHER


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


async def can_manage_character(repository: CharacterRepository, character_id: int, current_user: UserResponse) -> bool:
    """Whether ``current_user`` acts as this character's GM: the founder, or the GM of its active campaign."""

    if is_founder(current_user):
        return True
    if current_user.role != UserRole.GM:
        return False

    return await repository.is_managed_by(character_id, current_user.id)


async def check_owner_access(
    repository: CharacterRepository, character_id: int, owner_id: int, current_user: UserResponse
) -> None:
    """Raise ``CharacterAccessDeniedException`` unless the user owns the character or manages it (see module doc)."""

    if owner_id == current_user.id:
        return
    if not await can_manage_character(repository, character_id, current_user):
        raise CharacterAccessDeniedException()


async def check_character_access(
    repository: CharacterRepository, character: Character, current_user: UserResponse
) -> None:
    """Raise ``CharacterAccessDeniedException`` unless the user owns or manages ``character``."""

    await check_owner_access(repository, character.id, character.owner_id, current_user)


async def get_character_for_user(
    repository: CharacterRepository,
    character_id: int,
    current_user: UserResponse,
    *,
    light: bool = False,
) -> Character:
    """Fetch a character by ID and enforce access control in one call."""

    character = await get_character_or_404(repository, character_id, light=light)
    await check_character_access(repository, character, current_user)
    return character


async def get_character_for_gm(
    repository: CharacterRepository,
    character_id: int,
    current_user: UserResponse,
    *,
    light: bool = False,
) -> Character:
    """
    Fetch a character for a GM-panel write: the founder or the GM of the campaign it is ``ACTIVE`` in. Owning the
    character grants nothing here, so a GM playing in someone else's campaign can't raise their own cap or grant
    themselves feats and items (404 for a missing character, 403 otherwise).
    """

    character = await get_character_or_404(repository, character_id, light=light)
    if not await can_manage_character(repository, character.id, current_user):
        raise CharacterAccessDeniedException()
    return character


async def ensure_character_access(
    repository: CharacterRepository, character_id: int, current_user: UserResponse
) -> None:
    """
    Enforce owner/campaign-GM access without loading the character row: one
    ``owner_id`` lookup (plus the campaign lookup for a non-owner GM). For
    sub-resource endpoints that never read the character itself.
    """

    owner_id = await repository.get_owner_id(character_id)
    if owner_id is None:
        raise CharacterNotFoundException(character_id=character_id)

    await check_owner_access(repository, character_id, owner_id, current_user)
