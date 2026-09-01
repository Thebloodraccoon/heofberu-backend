"""Feat CRUD service: cached catalog CRUD plus composed capability writes."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.features.feats.asi.service import FeatAsiService
from app.features.feats.cache import FEAT_CACHE_NAMESPACES, invalidate_feat_cache
from app.features.feats.crud.repository import FeatRepository
from app.features.feats.schemas import (
    FeatCreate,
    FeatGetAllResponse,
    FeatResponse,
    FeatUpdate,
)
from app.models.feat_model import Feat

class FeatCrudService(CachedService[Feat, FeatCreate, FeatUpdate, FeatResponse, FeatGetAllResponse]):
    """
    Feat catalog CRUD built on :class:`CachedService`.

    Capability services are composed explicitly in ``__init__`` (no mixin
    MRO): ``create_feat`` seeds ``ability_score_increases`` through
    :class:`FeatAsiService` in the same ``_atomic()`` transaction. Feats
    own no features (a feat is de facto its own feature) so ``get_by_id``
    needs no override.
    """

    repository: FeatRepository

    cache_namespaces = FEAT_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Compose the feat ASI capability service."""

        super().__init__(
            repository=FeatRepository(db),
            response_schema=FeatResponse,
            get_all_schema=FeatGetAllResponse,
        )
        self._asi = FeatAsiService(db)

    async def create_feat(self, feat_data: FeatCreate) -> FeatResponse:
        """Create a feat after checking its name isn't already taken."""

        payload = feat_data.model_dump(exclude={"ability_score_increases"})

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

            if feat_data.ability_score_increases:
                increases = [
                    {"ability": inc.ability, "amount": inc.amount} for inc in feat_data.ability_score_increases
                ]
                await self._asi.set_ability_score_increases_for_feat(item, increases, commit=False)

        await invalidate_feat_cache()
        response = await self._get_response(item.id)

        # Warm the cache immediately: the write already paid for the transaction,
        # so the next GET hits cache instead of racing the invalidation.
        await self.get_by_id(item.id)

        return response
