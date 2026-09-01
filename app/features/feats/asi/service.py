"""Feat ASI service: full replacement of a feat's ability score increases."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.feats.cache import FEAT_CACHE_NAMESPACES, invalidate_feat_cache
from app.features.feats.crud.repository import FeatRepository
from app.features.feats.schemas import AbilityScoreIncreasesUpdate, FeatCreate, FeatResponse, FeatUpdate
from app.models.feat_model import Feat

class FeatAsiService(BaseService[Feat, FeatCreate, FeatUpdate, FeatResponse, None]):
    """
    Feat ASI service: full replacement of a feat's ability score increases.

    ``set_ability_score_increases`` is the public full-replace write; the
    ``commit=False`` variant is shared with ``create_feat``.
    """

    repository: FeatRepository

    cache_namespaces = FEAT_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize the service with the feat repository."""

        super().__init__(
            repository=FeatRepository(db),
            response_schema=FeatResponse,
        )

    async def set_ability_score_increases(self, feat_id: int, data: AbilityScoreIncreasesUpdate) -> FeatResponse:
        """Fully replace a feat's ASI choices."""

        feat = await self._get_or_404(feat_id)

        increases = [{"ability": item.ability, "amount": item.amount} for item in data.ability_score_increases]
        await self.repository.set_ability_score_increases(feat, increases)
        await invalidate_feat_cache()

        return await self._get_response(feat_id)

    async def set_ability_score_increases_for_feat(
        self, feat: Feat, increases: list[dict], *, commit: bool = True
    ) -> None:
        """Replace a feat's ASI choices on an existing ``feat`` row (used by ``create_feat``)."""

        await self.repository.set_ability_score_increases(feat, increases, commit=commit)
