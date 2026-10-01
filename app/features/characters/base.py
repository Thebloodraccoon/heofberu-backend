"""Shared base for character sub-domain services (access-control and transaction wiring)."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.transaction import UnitOfWork, atomic, unit_of_work
from app.features.characters.access import ensure_character_access
from app.features.characters.access import get_character_for_user as _get_character_for_user
from app.features.characters.cache import invalidate_character_cache
from app.features.characters.crud.repository import CharacterRepository
from app.features.users.schemas import UserResponse
from app.models.character.character_model import Character


class CharacterSubDomainService:
    """
    Base for character sub-domain services: owns the single ``CharacterRepository``,
    the GM/owner access checks and the transaction helpers.

    The service owns the transaction: multi-step writes run inside
    :meth:`_atomic` / :meth:`_unit_of_work` with ``commit=False`` repository
    calls, and cache purges go through :meth:`_invalidate_character` so they
    only run after the commit.
    """

    # ``populate_existing`` is skipped for the access-checked fetch; subclasses
    # that need a freshly re-read row set this to ``False``.
    _light_character_fetch = True

    def __init__(self, db: AsyncSession):
        """Create the shared ``CharacterRepository`` for the sub-domain."""

        self.repository = CharacterRepository(db)

    @asynccontextmanager
    async def _atomic(self) -> AsyncGenerator[None, None]:
        """One all-or-nothing transaction (see :func:`app.core.base.transaction.atomic`)."""

        async with atomic(self.repository.db):
            yield

    @asynccontextmanager
    async def _unit_of_work(self) -> AsyncGenerator[UnitOfWork, None]:
        """:meth:`_atomic` that yields a :class:`UnitOfWork` for post-commit side effects."""

        async with unit_of_work(self.repository.db) as uow:
            yield uow

    async def _invalidate_character(self, character_id: int) -> None:
        """Drop the character's cached response (deferred until commit inside an atomic block)."""

        await invalidate_character_cache(character_id, db=self.repository.db)

    async def get_character_for_user(self, character_id: int, current_user: UserResponse) -> Character:
        """Fetch the character enforcing GM/owner access; raises 403/404 otherwise."""

        return await _get_character_for_user(
            self.repository,
            character_id,
            current_user,
            light=self._light_character_fetch,
        )

    async def ensure_character_access(self, character_id: int, current_user: UserResponse) -> None:
        """Enforce GM/owner access without loading the character row (404/403 otherwise)."""

        await ensure_character_access(self.repository, character_id, current_user)
