"""Subrace CRUD service: cached catalog CRUD plus composed capability reads."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.core.cache import use_cache
from app.core.cache.client import cache_prefix
from app.core.exceptions import RecordNotFoundError
from app.features.features.crud.service import FeatureCrudService
from app.features.races.crud.repository import RaceRepository
from app.features.subraces.cache import SUBRACE_CACHE_NAMESPACES, invalidate_subrace_cache
from app.features.subraces.crud.repository import SubraceRepository
from app.features.subraces.crud.schemas import (
    SubraceCreate,
    SubraceGetAllResponse,
    SubraceResponse,
    SubraceUpdate,
)
from app.models.races.subrace_model import Subrace


class SubraceCrudService(
    BaseService[Subrace, SubraceCreate, SubraceUpdate, SubraceResponse, None],
):
    """Subrace catalog CRUD with race-scoped lookups."""

    repository: SubraceRepository

    cache_namespaces = SUBRACE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize composed feature and race-repository services."""

        super().__init__(
            repository=SubraceRepository(db),
            response_schema=SubraceResponse,
        )
        self._features = FeatureCrudService(db)
        self._race_repository = RaceRepository(db)

    async def list_for_race(self, race_id: int) -> list[SubraceGetAllResponse]:
        """Return every subrace belonging to ``race_id``, without their ability bonuses."""

        await self._ensure_race_exists(race_id)
        return [
            SubraceGetAllResponse.model_validate(subrace) for subrace in await self.repository.list_for_race(race_id)
        ]

    @use_cache(key_builder=lambda self, item_id: f"{cache_prefix()}:races:subrace:get_by_id:{item_id}")
    async def get_by_id(self, item_id: int) -> SubraceResponse:
        """Return a subrace with its ability bonuses and SUBRACE-source features (cached)."""

        subrace = await self._get_or_404(item_id)
        features = await self._features.list_for_source(FeatureSourceType.SUBRACE, item_id)

        return SubraceResponse.model_validate(
            {**SubraceResponse.model_validate(subrace).model_dump(), "features": features}
        )

    async def create_subrace(self, data: SubraceCreate) -> SubraceResponse:
        """
        Create a subrace under ``race_id`` (base fields only).

        ``ability_bonuses`` and ``features`` are not seeded here — each is
        attached afterwards through its own capability endpoint.
        """

        await self._ensure_race_exists(data.race_id)

        item = await self.repository.create(data.model_dump())
        await invalidate_subrace_cache()

        return await self._get_response(item.id)

    async def _ensure_race_exists(self, race_id: int) -> None:
        """Raise ``RecordNotFoundError`` when no race with ``race_id`` exists."""

        if not await self._race_repository.exists_by_id(race_id):
            raise RecordNotFoundError(model_name="Race", model_id=str(race_id))
