"""Feat CRUD service: cached catalog CRUD plus composed capability reads."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.core.cache import use_cache
from app.features.feats.asi.service import FeatAsiService
from app.features.feats.cache import FEAT_CACHE_NAMESPACES, invalidate_feat_cache
from app.features.feats.crud.repository import FeatRepository
from app.features.feats.features.service import FeatFeatureService
from app.features.feats.schemas import (
    FeatCreate,
    FeatFullResponse,
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
    mixin MRO):
      - ``get_by_id`` reads the FEAT-source ``features`` through
        :class:`FeatFeatureService` — the cached nested listing — and
        assembles :class:`FeatFullResponse`;
      - ``create_feat`` seeds ``ability_score_increases`` through
        :class:`FeatAsiService` in the same ``_atomic()`` transaction.

    ``cache_namespaces`` covers the two namespaces any feat read hits (the
    same blunt whole-namespace invalidation the previous service used); the
    capability services use :func:`invalidate_feat_cache` explicitly for
    their own writes.
    """

    repository: FeatRepository

    cache_namespaces = FEAT_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=FeatRepository(db),
            response_schema=FeatResponse,
            get_all_schema=FeatGetAllResponse,
        )
        self._features = FeatFeatureService(db)
        self._asi = FeatAsiService(db)

    async def create_feat(self, feat_data: FeatCreate, created_by_id: int | None = None) -> FeatResponse:
        """
        Create a feat after checking its name isn't already taken.

        ``created_by_id`` identifies the GM who created it and is not part
        of ``FeatCreate`` itself, since it comes from the authenticated
        user, not client input.

        Kept minimal on purpose: only the feat's own scalar fields plus
        ``ability_score_increases`` (a simple child table, not a nested
        dependency) are set here, atomically, alongside the ``Feat`` row
        itself — via :class:`FeatAsiService` so the ASI write path stays in
        one place.

        ``features`` is NOT part of create — attach them afterwards through
        ``POST /feats/{id}/features``.
        """

        payload = feat_data.model_dump(exclude={"ability_score_increases"})
        payload["created_by_id"] = created_by_id

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

    @use_cache()
    async def get_by_id(self, item_id: int) -> FeatFullResponse:
        """
        Return a feat with its own FEAT-source ``features`` included — this
        overrides ``BaseService.get_by_id`` (which only returns bare
        ``FeatResponse`` fields via a plain ``model_validate``) so
        ``GET /feats/{id}`` itself is the full picture: base fields,
        ability_score_increases, and features.

        Any write that touches this feat (base fields, ASI choices,
        features) invalidates the ``feats`` namespace via
        :func:`invalidate_feat_cache` / ``cache_namespaces`` — the same
        blunt, whole-namespace invalidation the rest of this service uses
        for reference-catalog data (infrequent writes, frequent reads).
        """

        feat = await self._get_or_404(item_id)
        features = await self._features.list_features(item_id)

        return FeatFullResponse.model_validate({**FeatResponse.model_validate(feat).model_dump(), "features": features})
