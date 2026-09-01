"""Feature ability-increase service: read + full replacement of a feature's fixed effects."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.characters.progression.feature_sync import refresh_feature_effect_caches
from app.features.features.ability_increases.schemas import (
    AbilityIncreasesUpdate,
    FeatureAbilityIncreasesResponse,
)
from app.features.features.cache import FEATURE_CACHE_NAMESPACES, invalidate_feature_cache
from app.features.features.crud.repository import FeatureRepository
from app.features.features.crud.schemas import FeatureResponse
from app.models.feature_model import Feature

class FeatureAbilityIncreaseService(BaseService[Feature, None, None, FeatureResponse, None]):
    """
    Everything about a feature's fixed ability-score increases.

    Effects are automatic: while the feature is granted to a character
    (``character_features``), every row adds its ``amount`` to the effective
    total and may raise the ability's cap (``new_cap``). ``set_ability_increases``
    is a full replace; any write purges the ``features`` namespace AND
    refreshes the stat caches of every character currently granted the
    feature (the same known one-way import compromise as ``FeatureCrudService``
    importing ``characters/progression/feature_sync`` — no import cycle).
    """

    repository: FeatureRepository

    cache_namespaces = FEATURE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize the service with the feature repository."""

        super().__init__(
            repository=FeatureRepository(db),
            response_schema=FeatureResponse,
        )

    async def get_ability_increases(self, feature_id: int) -> FeatureAbilityIncreasesResponse:
        """Return a feature's fixed ability-score increases."""

        feature = await self._get_or_404(feature_id)
        return FeatureAbilityIncreasesResponse(
            feature_id=feature.id,
            ability_increases=list(feature.ability_increases),
        )

    async def set_ability_increases(
        self, feature_id: int, data: AbilityIncreasesUpdate
    ) -> FeatureAbilityIncreasesResponse:
        """Fully replace a feature's fixed ability-score increases."""

        feature = await self._get_or_404(feature_id)

        await self.repository.set_ability_increases(
            feature,
            [
                {"ability": item.ability, "amount": item.amount, "new_cap": item.new_cap}
                for item in data.ability_increases
            ],
            commit=False,
        )
        # Refresh the stat caches of every character granted this feature
        # in the same transaction (never commits on its own).
        await refresh_feature_effect_caches(self.repository.db, feature_id)
        await self.repository.db.commit()
        await invalidate_feature_cache()

        return await self.get_ability_increases(feature_id)
