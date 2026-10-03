"""Subrace CRUD service: cached detail read plus race-scoped listing and writes."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.core.cache import use_cache
from app.core.cache.client import cache_prefix
from app.core.exceptions import RecordNotFoundError
from app.core.storage.service import ImageStorageService
from app.features.shared.catalog.cache import CatalogCacheMixin, purge_after_commit
from app.features.subraces.cache import SUBRACE_CRUD_CACHE_NAMESPACES, SUBRACE_DELETE_NAMESPACES
from app.features.subraces.crud.repository import SubraceRepository
from app.features.subraces.crud.schemas import (
    SubraceCreate,
    SubraceGetAllResponse,
    SubraceResponse,
    SubraceUpdate,
)
from app.models.races.subrace_model import Subrace


class SubraceCrudService(
    CatalogCacheMixin,
    BaseService[Subrace, SubraceCreate, SubraceUpdate, SubraceResponse],
):
    """Subrace catalog CRUD with race-scoped lookups."""

    repository: SubraceRepository

    cache_namespaces = SUBRACE_CRUD_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession, storage: ImageStorageService | None = None):
        """Initialize the subrace repository; ``storage`` (optional) removes images of deleted subraces."""

        super().__init__(
            repository=SubraceRepository(db),
            response_schema=SubraceResponse,
        )
        self._storage = storage

    async def list_for_race(self, race_id: int) -> list[SubraceGetAllResponse]:
        """Return every subrace belonging to ``race_id``, without their ability bonuses."""

        await self._ensure_race_exists(race_id)
        return [
            SubraceGetAllResponse.model_validate(subrace) for subrace in await self.repository.list_for_race(race_id)
        ]

    # Own key: the default one would collide with ``RaceCrudService.get_by_id`` in the shared ``races`` namespace.
    @use_cache(key_builder=lambda self, item_id: f"{cache_prefix()}:races:subrace:get_by_id:{item_id}")
    async def get_by_id(self, item_id: int) -> SubraceResponse:
        """Return a subrace with its ability bonuses, tags and SUBRACE-source features (cached)."""

        return SubraceResponse.model_validate(await self._get_or_404(item_id))

    async def create_subrace(self, data: SubraceCreate) -> SubraceResponse:
        """
        Create a subrace under ``race_id`` (base fields only).

        ``ability_bonuses`` and ``features`` are not seeded here: each is
        attached afterwards through its own capability endpoint.
        """

        await self._ensure_race_exists(data.race_id)

        item = await self.repository.create(data.model_dump())
        await self._invalidate_cache()

        return await self._get_response(item.id)

    async def delete(self, item_id: int) -> bool:
        """Delete a subrace (blocked while characters use it), purge what the cascade removed, drop its image."""

        subrace = await self._get_or_404(item_id)

        await self.repository.delete(subrace)
        await purge_after_commit(self.repository.db, *SUBRACE_DELETE_NAMESPACES)

        if self._storage is not None:
            await self._storage.delete_image("subraces", item_id)

        return True

    async def _ensure_race_exists(self, race_id: int) -> None:
        """Raise ``RecordNotFoundError`` when no race with ``race_id`` exists."""

        if not await self.repository.race_exists(race_id):
            raise RecordNotFoundError(model_name="Race", model_id=str(race_id))
