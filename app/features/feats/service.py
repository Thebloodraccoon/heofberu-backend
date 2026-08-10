"""Feat CRUD service including ASI-choice management."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.cached_service import CachedService
from app.features.feats.repository import FeatRepository
from app.features.feats.schemas import (
    AbilityScoreIncreasesUpdate,
    FeatCreate,
    FeatGetAllResponse,
    FeatResponse,
    FeatUpdate,
)
from app.features.features.mixins import SourceFeatureMixin
from app.features.features.nested_service import NestedFeatureService
from app.models.feat_model import Feat


class FeatService(
    SourceFeatureMixin,
    CachedService[Feat, FeatCreate, FeatUpdate, FeatResponse, FeatGetAllResponse],
):
    """
    Feat-specific CRUD service built on :class:`CachedService`.

    Mirrors ``RaceService``: a uniqueness check on ``name`` before
    create/update, management of ``ability_score_increases`` (its own
    child table, no generic base-class equivalent, set up in the same
    transaction as the feat via ``BaseService._atomic()``), per-source
    feature CRUD (``add_feature``/``update_feature``/``remove_feature``)
    and per-source feature listing (``list_features``) from
    :class:`SourceFeatureMixin`, and a delete guard blocking removal of a
    feat still granted to any character or whose features are still
    granted to a character (its own ``features`` rows cascade away with
    the feat).

    Listing and detail reads are cached via ``@use_cache``. The feat
    responses no longer embed their ``features`` — they are read through
    ``list_features`` (cached under the dedicated ``nested_features``
    namespace), so the service invalidates both its own namespace and
    ``nested_features`` on catalog writes.
    """

    repository: FeatRepository

    cache_namespaces = ("feats", "nested_features")

    _feature_source_type = FeatureSourceType.FEAT

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=FeatRepository(db),
            response_schema=FeatResponse,
            get_all_schema=FeatGetAllResponse,
        )
        self._features = NestedFeatureService(db)

    async def create_feat(self, feat_data: FeatCreate, created_by_id: int | None = None) -> FeatResponse:
        """
        Create a feat after checking its name isn't already taken.

        ``feat_data.ability_score_increases`` / ``feat_data.features`` are
        optional. If supplied, they're set in the same transaction as the
        feat itself via ``BaseService._atomic()`` — same reasoning as
        ``RaceService.create_race``. Nested features are created through
        ``FeatureService.create_features_for_source`` with
        ``source_type=FEAT``.
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

            await self._features.create_features_for_source(
                FeatureSourceType.FEAT,
                item.id,
                feat_data.features,
                created_by_id,
                commit=False,
            )

        await self._invalidate_cache()

        return await self._get_response(item.id)

    async def set_ability_score_increases(self, feat_id: int, data: AbilityScoreIncreasesUpdate) -> FeatResponse:
        """Fully replace a feat's ASI choices."""

        feat = await self._get_or_404(feat_id)

        increases = [{"ability": item.ability, "amount": item.amount} for item in data.ability_score_increases]
        await self.repository.set_ability_score_increases(feat, increases)
        await self._invalidate_cache()

        return await self._get_response(feat_id)
