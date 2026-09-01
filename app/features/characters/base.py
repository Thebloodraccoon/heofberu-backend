"""Shared base for character sub-domain services (access-control wiring)."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import atomic
from app.features.characters.access import get_character_for_user as _get_character_for_user
from app.features.characters.crud.repository import CharacterRepository
from app.features.users.schemas import UserResponse
from app.models.character_model import Character


class CharacterSubDomainService:
    """Shared base for character sub-domain services: owns the single ``CharacterRepository`` and exposes the light GM/owner access-checked character fetch."""

    _light_character_fetch = True

    def __init__(self, db: AsyncSession):
        """Create the shared ``CharacterRepository`` for the sub-domain."""

        self.repository = CharacterRepository(db)

    @asynccontextmanager
    async def _atomic(self) -> AsyncGenerator[None, None]:
        """Shared savepoint transaction (delegates to :func:`app.core.base.service.atomic`)."""

        async with atomic(self.repository.db):
            yield

    async def get_character_for_user(self, character_id: int, current_user: UserResponse) -> Character:
        """Fetch the character enforcing GM/owner access; raises 403/404 otherwise."""

        return await _get_character_for_user(
            self.repository,
            character_id,
            current_user,
            light=self._light_character_fetch,
        )
