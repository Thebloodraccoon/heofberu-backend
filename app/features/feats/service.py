"""Feat CRUD service including ASI-choice management."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base_service import BaseService, Page
from app.core.cache import use_cache
from app.features.characters.progression.feature_sync import reconcile_characters_for_source
from app.features.feats.repository import FeatRepository
from app.features.feats.schemas import (
    AbilityScoreIncreasesUpdate,
    FeatCreate,
    FeatGetAllResponse,
    FeatResponse,
    FeatUpdate,
)
from app.features.features.schemas import FeaturesReplace
from app.features.features.service import create_features_for_source, replace_features_for_source
from app.models.feat_model import Feat


class FeatService(BaseService[Feat, FeatCreate, FeatUpdate, FeatResponse, FeatGetAllResponse]):
    """
    Feat-specific CRUD service built on :class:`BaseService`.

    Mirrors ``RaceService``: a uniqueness check on ``name`` before
    create/update, management of ``ability_score_increases`` (its own
    child table, no generic base-class equivalent, set up in the same
    transaction as the feat via ``BaseService._atomic()``), and a delete
    guard blocking removal of a feat still granted to any character or
    whose features are still granted to a character (its own
    ``features`` rows cascade away with the feat).

    Listing and detail reads are cached via ``@use_cache``. Because a
    feat's writes also touch the ``features`` table (FEAT-source rows),
    the service invalidates both its own namespace and ``features``.
    """

    repository: FeatRepository

    cache_namespaces = ("feats", "features")

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=FeatRepository(db),
            response_schema=FeatResponse,
            get_all_schema=FeatGetAllResponse,
        )

    @use_cache()
    async def get_all(
        self,
        page: int = 1,
        size: int = 100,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
    ) -> Page[FeatGetAllResponse]:
        """Cached lightweight listing — see ``BaseService.get_all``."""

        return await super().get_all(page=page, size=size, filters=filters, search=search)

    @use_cache()
    async def get_by_id(self, item_id: int) -> FeatResponse:
        """Cached single-record fetch — see ``BaseService.get_by_id``."""

        return await super().get_by_id(item_id)

    async def create_feat(self, feat_data: FeatCreate, created_by_id: int | None = None) -> FeatResponse:
        """
        Create a feat after checking its name isn't already taken.

        ``feat_data.ability_score_increases`` / ``feat_data.features`` are
        optional. If supplied, they're set in the same transaction as the
        feat itself via ``BaseService._atomic()`` — same reasoning as
        ``RaceService.create_race``. Nested features are created through
        ``create_features_for_source`` with ``source_type=FEAT``.
        """

        payload = feat_data.model_dump(exclude={"ability_score_increases", "features"})
        payload["created_by_id"] = created_by_id

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

            if feat_data.ability_score_increases:
                increases = [
                    {"ability": inc.ability, "amount": inc.amount} for inc in feat_data.ability_score_increases
                ]
                await self.repository.set_ability_score_increases(item, increases, commit=False)

            await create_features_for_source(
                self.repository.db,
                FeatureSourceType.FEAT,
                item.id,
                feat_data.features,
                created_by_id,
                commit=False,
            )

        await self._invalidate_cache()

        return self.response_schema.model_validate(await self._get_or_404(item.id))

    async def set_ability_score_increases(self, feat_id: int, data: AbilityScoreIncreasesUpdate) -> FeatResponse:
        """Fully replace a feat's ASI choices."""

        feat = await self._get_or_404(feat_id)

        increases = [{"ability": item.ability, "amount": item.amount} for item in data.ability_score_increases]
        await self.repository.set_ability_score_increases(feat, increases)
        await self._invalidate_cache()

        return self.response_schema.model_validate(await self._get_or_404(feat_id))

    async def replace_feat_features(
        self, feat_id: int, data: FeaturesReplace, created_by_id: int | None = None
    ) -> FeatResponse:
        """
        Full-replace a feat's FEAT-source features, matched by feature id.

        Items carrying an ``id`` update that feature in place — the id is
        kept, so character grants and any player notes on them survive.
        Items without an ``id`` create new features; existing features
        whose id is absent from the payload are deleted, cascading their
        grants away. Runs atomically, then reconciles the grants of every
        character holding this feat so their builds match the new feature
        set.
        """

        feat = await self._get_or_404(feat_id)
        async with self._atomic():
            await replace_features_for_source(
                self.repository.db,
                FeatureSourceType.FEAT,
                feat.id,
                data.features,
                created_by_id,
                commit=False,
            )
            await reconcile_characters_for_source(self.repository.db, FeatureSourceType.FEAT, feat.id)

        await self._invalidate_cache()

        self.repository.db.expire(feat)
        return self.response_schema.model_validate(await self._get_or_404(feat_id))
