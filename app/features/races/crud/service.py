"""Race CRUD service: cached catalog CRUD plus composed capability reads."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.features.races.cache import RACE_CACHE_NAMESPACES, invalidate_race_cache
from app.features.races.crud.repository import RaceRepository
from app.features.races.crud.schemas import (
    RaceCreate,
    RaceGetAllResponse,
    RaceResponse,
    RaceUpdate,
)
from app.models.races.race_model import Race


class RaceCrudService(
    CachedService[Race, RaceCreate, RaceUpdate, RaceResponse, RaceGetAllResponse],
):
    """Race catalog CRUD."""

    repository: RaceRepository

    cache_namespaces = RACE_CACHE_NAMESPACES
    get_all_order_by = "name"

    def __init__(self, db: AsyncSession):
        """Initialize the race repository."""

        super().__init__(
            repository=RaceRepository(db),
            response_schema=RaceResponse,
            get_all_schema=RaceGetAllResponse,
        )

    async def create_race(self, race_data: RaceCreate) -> RaceResponse:
        """
        Create a race (base fields only).

        ``ability_bonuses``, ``granted_skills``, and ``features`` are not
        seeded here — each is attached afterwards through its own
        capability endpoint.
        """

        item = await self.repository.create(race_data.model_dump())
        await invalidate_race_cache()

        return await self._get_response(item.id)
