"""Feat ASI service: full replacement of a feat's ability score increases."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RecordNotFoundError
from app.features.feats.cache import invalidate_feat_cache
from app.features.feats.crud.repository import FeatRepository
from app.features.feats.schemas import AbilityScoreIncreasesUpdate, FeatResponse
from app.features.features.cache import invalidate_feature_cache
from app.models.feature_model import Feature


class FeatAsiService:
    """
    Feat ASI service: full replacement of a feat's ability score increases
    (modeled on the engine as a single ``pick_count=1`` choice group — see
    ``FeatRepository.set_ability_score_increases``).

    ``set_ability_score_increases`` is the public full-replace write; the
    ``commit=False`` variant is shared with ``FeatCrudService.create_feat``.
    """

    def __init__(self, db: AsyncSession):
        """Initialize the service with the feat repository."""

        self.repository = FeatRepository(db)

    async def set_ability_score_increases(self, feat_id: int, data: AbilityScoreIncreasesUpdate) -> FeatResponse:
        """Fully replace a feat's ASI choices."""

        # Local import: avoids a service-to-service import cycle at module load
        # (FeatCrudService already owns a FeatAsiService instance).
        from app.features.feats.crud.service import _to_feat_response

        feat = await self.repository.get_by_id(feat_id)
        if feat is None:
            raise RecordNotFoundError(model_name="Feat", model_id=str(feat_id))

        increases = [{"ability": item.ability, "amount": item.amount} for item in data.ability_score_increases]
        await self.repository.set_ability_score_increases(feat, increases)
        await invalidate_feat_cache()
        await invalidate_feature_cache()

        feat = await self.repository.get_by_id(feat_id)
        return _to_feat_response(feat)

    async def set_ability_score_increases_for_feat(
        self, feat: Feature, increases: list[dict], *, commit: bool = True
    ) -> None:
        """Replace a feat's ASI choices on an existing ``feat`` row (used by ``create_feat``)."""

        await self.repository.set_ability_score_increases(feat, increases, commit=commit)
