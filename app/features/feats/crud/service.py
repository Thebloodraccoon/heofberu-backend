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


class FeatCrudService(
    CachedService[Feat, FeatCreate, FeatUpdate, FeatResponse, FeatGetAllResponse],
):
    """
    Feat catalog CRUD built on :class:`CachedService`.

    The capability services are composed explicitly in ``__init__`` (no
    mixin MRO): ``create_feat`` seeds ``ability_score_increases`` through
    :class:`FeatAsiService` in the same ``_atomic()`` transaction.

    Feats own no features — a feat is de facto its own feature, the
    content lives in its description. ``get_by_id`` therefore needs no
    override: the base ``CachedService`` read returns ``FeatResponse``
    directly.

    ``cache_namespaces`` covers the one namespace any feat read hits; the
    ASI capability uses :func:`invalidate_feat_cache` explicitly for its
    own writes.
    """

    repository: FeatRepository

    cache_namespaces = FEAT_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=FeatRepository(db),
            response_schema=FeatResponse,
            get_all_schema=FeatGetAllResponse,
        )
        self._asi = FeatAsiService(db)

    async def create_feat(self, feat_data: FeatCreate) -> FeatResponse:
        """
        Create a feat after checking its name isn't already taken.

        Kept minimal on purpose: only the feat's own scalar fields plus
        ``ability_score_increases`` (a simple child table, not a nested
        dependency) are set here, atomically, alongside the ``Feat`` row
        itself — via :class:`FeatAsiService` so the ASI write path stays in
        one place.
        """

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

        # Warm the cache immediately: the write already paid for the
        # transaction, so pre-populating it here means the very next GET
        # (which is likely right after a create) hits cache instead of
        # racing the invalidation into a cold read.
        await self.get_by_id(item.id)

        return response
