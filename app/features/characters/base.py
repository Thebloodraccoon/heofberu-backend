"""Shared base for character sub-domain services (access-control wiring)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.characters.access import get_character_for_user as _get_character_for_user
from app.features.characters.crud.repository import CharacterRepository
from app.features.users.schemas import UserResponse
from app.models.character_model import Character


class CharacterSubDomainService:
    """
    Shared base for the character sub-domain services (attacks, feats,
    spells, conditions).

    Every sub-domain service needs the *owning* character for access
    control (the GM/owner check) before touching its own tables. Before
    this base existed, each service constructed its own
    ``CharacterRepository(db)`` and imported ``get_character_for_user``
    separately — four copies of the same wiring. This base owns the
    single ``CharacterRepository`` and exposes
    :meth:`get_character_for_user`, which both enforces access and
    returns the character.

    ``repository`` is kept as an attribute name (rather than
    ``character_repository``) so existing sub-service code that stored
    the same repository under ``self.repository`` keeps working
    unchanged.

    Sub-domain services only ever need the character's scalar columns
    (access check, ``level``/``class_id``/``race_id`` and so on), so the
    shared fetch uses the light lookup — no eager-loading the four
    collection relationships, which cost four queries per call. A
    subclass that serializes a full ``CharacterResponse`` overrides
    ``_light_character_fetch`` to ``False``.
    """

    _light_character_fetch = True

    def __init__(self, db: AsyncSession):
        self.repository = CharacterRepository(db)

    async def get_character_for_user(self, character_id: int, current_user: UserResponse) -> Character:
        """Fetch the character enforcing GM/owner access; raises 403/404 otherwise."""

        return await _get_character_for_user(
            self.repository,
            character_id,
            current_user,
            light=self._light_character_fetch,
        )
