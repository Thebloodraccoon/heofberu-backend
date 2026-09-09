"""Feat CRUD service: cached catalog CRUD over the unified Feature/Feat engine."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService, Page, paginate
from app.core.cache import use_cache
from app.features.feats.asi.service import FeatAsiService
from app.features.feats.cache import FEAT_CACHE_NAMESPACES, invalidate_feat_cache
from app.features.feats.crud.repository import FeatRepository, feat_ability_score_effects
from app.features.feats.schemas import (
    AbilityScoreIncreaseResponse,
    FeatCreate,
    FeatGetAllResponse,
    FeatResponse,
    FeatUpdate,
)
from app.features.features.cache import invalidate_feature_cache
from app.models.feature_model import Feature


def _flatten_ability_score_increases(feature: Feature) -> list[AbilityScoreIncreaseResponse]:
    """
    Flatten a FEAT feature's engine ability-score effects into the response
    shape the API has always returned. The item's ``id`` is the
    ``feature_ability_score_effects`` row id (what a character grant's
    ``ability_score_increase_id`` points at).
    """

    return [
        AbilityScoreIncreaseResponse(id=effect.id, ability=effect.ability, amount=effect.amount)
        for effect in feat_ability_score_effects(feature)
    ]


def _to_feat_response(feature: Feature) -> FeatResponse:
    """Build a ``FeatResponse`` from a FEAT-source ``Feature`` row."""

    return FeatResponse(
        id=feature.id,
        name=feature.name,
        description=feature.description,
        prerequisite_ability=feature.prerequisite_ability,
        prerequisite_minimum_score=feature.prerequisite_minimum_score,
        prerequisite_description=feature.prerequisite_description,
        min_level=feature.min_level,
        ability_score_increases=_flatten_ability_score_increases(feature),
    )


def _to_feat_brief(feature: Feature) -> FeatGetAllResponse:
    """Build a ``FeatGetAllResponse`` (listing row) from a FEAT-source ``Feature`` row."""

    return FeatGetAllResponse(
        id=feature.id,
        name=feature.name,
        min_level=feature.min_level,
        ability_score_increases=_flatten_ability_score_increases(feature),
    )


class FeatCrudService(BaseService[Feature, FeatCreate, FeatUpdate, FeatResponse, FeatGetAllResponse]):
    """
    Feat catalog CRUD, built directly on ``Feature`` (``source_type=FEAT``).

    Unlike most ``CachedService`` catalogs, ``get_all``/``get_by_id``/
    ``update`` are overridden rather than inherited: the generic base
    serializes straight off ORM attributes matching the schema's field
    names, but a feat's ``ability_score_increases`` is a *computed*
    flattening of the engine's choice-group tree (see
    ``_flatten_ability_score_increases``), not a same-named relationship on
    ``Feature``. Every write purges both the ``feats`` namespace and the
    shared ``features`` namespace (``GET /features`` reads the same table).
    """

    repository: FeatRepository

    cache_namespaces = FEAT_CACHE_NAMESPACES
    get_all_order_by = "name"

    def __init__(self, db: AsyncSession):
        """Compose the feat ASI capability service."""

        super().__init__(
            repository=FeatRepository(db),
            response_schema=FeatResponse,
            get_all_schema=FeatGetAllResponse,
        )
        self._asi = FeatAsiService(db)

    async def create_feat(self, feat_data: FeatCreate) -> FeatResponse:
        """Create a feat (as a FEAT-source ``Feature``) after checking its name isn't already taken."""

        payload = feat_data.model_dump(exclude={"ability_score_increases"})

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

            if feat_data.ability_score_increases:
                increases = [
                    {"ability": inc.ability, "amount": inc.amount} for inc in feat_data.ability_score_increases
                ]
                await self._asi.set_ability_score_increases_for_feat(item, increases, commit=False)

        await self._invalidate_all()

        return await self._get_response_for(item.id)

    @use_cache()
    async def get_all(
        self, page: int = 1, size: int = 100, filters: dict | None = None, search: str | None = None
    ) -> Page[FeatGetAllResponse]:
        """Cached, paginated feat listing."""

        skip, limit = paginate(page, size)
        total = await self.repository.count(filters=filters, search=search)
        items = await self.repository.get_all(
            skip=skip, limit=limit, filters=filters, search=search, order_by=Feature.name
        )
        return Page(items=[_to_feat_brief(item) for item in items], total=total, page=page, size=size)

    @use_cache()
    async def get_by_id(self, item_id: int) -> FeatResponse:
        """Cached single-feat fetch."""

        return await self._get_response_for(item_id)

    async def update(self, item_id: int, update_data: FeatUpdate) -> FeatResponse:
        """Partially update a feat's base fields (never its ASI options — see the dedicated endpoint)."""

        item = await self._get_or_404(item_id)
        fields = update_data.model_dump(exclude_unset=True)

        updated_item = await self.repository.update(item, fields)
        await self._invalidate_all()

        return await self._get_response_for(updated_item.id)

    async def delete(self, item_id: int) -> bool:
        """Delete a feat, blocked while any character still holds it."""

        item = await self._get_or_404(item_id)
        result = await self.repository.delete(item)
        await self._invalidate_all()

        return result

    async def _get_response_for(self, item_id: int) -> FeatResponse:
        """Re-fetch (with the engine effect tree loaded) and serialize to ``FeatResponse``."""

        item = await self._get_or_404(item_id)
        return _to_feat_response(item)

    async def _invalidate_all(self) -> None:
        """Purge both the ``feats`` namespace and the shared ``features`` namespace (same underlying table)."""

        await invalidate_feat_cache()
        await invalidate_feature_cache()
