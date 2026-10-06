"""Race CRUD service: cached catalog CRUD with exact post-commit cache purges."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.core.storage.service import ImageStorageService
from app.features.races.cache import RACE_CRUD_CACHE_NAMESPACES, RACE_DELETE_NAMESPACES
from app.features.races.crud.repository import RaceRepository
from app.features.races.crud.schemas import (
    RaceCreate,
    RaceGetAllResponse,
    RaceResponse,
    RaceUpdate,
)
from app.features.shared.catalog.cache import CatalogCacheMixin, purge_after_commit
from app.models.races.race_model import Race


class RaceCrudService(
    CatalogCacheMixin,
    CachedService[Race, RaceCreate, RaceUpdate, RaceResponse, RaceGetAllResponse],
):
    """Race catalog CRUD."""

    repository: RaceRepository

    cache_namespaces = RACE_CRUD_CACHE_NAMESPACES
    get_all_order_by = "name"

    def __init__(self, db: AsyncSession, storage: ImageStorageService | None = None):
        """Initialize the race repository; ``storage`` (optional) removes images of deleted races."""

        super().__init__(
            repository=RaceRepository(db),
            response_schema=RaceResponse,
            get_all_schema=RaceGetAllResponse,
        )
        self._storage = storage

    async def create_race(self, race_data: RaceCreate) -> RaceResponse:
        """
        Create a race (base fields only).

        ``ability_bonuses``, ``granted_skills``, and ``features`` are not
        seeded here — each is attached afterwards through its own
        capability endpoint.
        """

        async with self._atomic():
            item = await self.repository.create(race_data.model_dump())
            await self._invalidate_cache()

        return await self._get_response(item.id)

    async def delete(self, item_id: int) -> bool:
        """Delete a race (blocked while characters use it), purge what the cascade removed, drop the images."""

        race = await self._get_or_404(item_id)
        subrace_ids = await self.repository.list_subrace_ids(item_id)

        async with self._atomic():
            await self.repository.delete(race)
            await purge_after_commit(self.repository.db, *RACE_DELETE_NAMESPACES)

        if self._storage is not None:
            await self._storage.delete_image("races", item_id)
            for subrace_id in subrace_ids:
                await self._storage.delete_image("subraces", subrace_id)

        return True
