"""Feat CRUD service: cached catalog CRUD over the unified Feature/Feat engine."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService, Page, paginate
from app.core.cache import use_cache
from app.features.feats.cache import FEAT_CACHE_NAMESPACES, invalidate_feat_cache
from app.features.feats.crud.repository import FeatRepository
from app.features.feats.crud.schemas import FeatCreate, FeatGetAllResponse, FeatResponse, FeatUpdate
from app.features.features.cache import invalidate_feature_cache
from app.models.features.feature_model import Feature


def _to_feat_response(feature: Feature) -> FeatResponse:
    """
    Build a ``FeatResponse`` from a FEAT-source ``Feature`` row.

    ``choice_groups``/``static_groups``/``has_static_effects``/``has_choices``/
    ``effects_summary`` come straight off the ``Feature`` ORM row (same
    properties ``GET /features/{id}`` serializes), off the eager-loaded
    engine relationships.
    """

    return FeatResponse.model_validate(
        {
            "id": feature.id,
            "name": feature.name,
            "description": feature.description,
            "prerequisite_ability": feature.prerequisite_ability,
            "prerequisite_minimum_score": feature.prerequisite_minimum_score,
            "prerequisite_description": feature.prerequisite_description,
            "min_level": feature.min_level,
            "choice_groups": feature.choice_groups,
            "static_groups": feature.static_groups,
            "has_static_effects": feature.has_static_effects,
            "has_choices": feature.has_choices,
            "effects_summary": feature.effects_summary,
        }
    )


def _to_feat_brief(feature: Feature) -> FeatGetAllResponse:
    """Build a ``FeatGetAllResponse`` (listing row) from a FEAT-source ``Feature`` row."""

    return FeatGetAllResponse(
        id=feature.id,
        name=feature.name,
        min_level=feature.min_level,
        has_static_effects=feature.has_static_effects,
        has_choices=feature.has_choices,
    )


class FeatCrudService(BaseService[Feature, FeatCreate, FeatUpdate, FeatResponse, FeatGetAllResponse]):
    """
    Feat catalog CRUD, built directly on ``Feature`` (``source_type=FEAT``).

    ``get_all``/``get_by_id``/``update`` are overridden rather than
    inherited so listing/detail rows can be scoped to FEAT-source ``Feature``
    rows and serialized via the shared ``_to_feat_brief``/``_to_feat_response``
    helpers (same ``has_static_effects``/``has_choices``/``static_groups``
    shape ``GET /features`` exposes). Every write purges both the ``feats``
    namespace and the shared ``features`` namespace (``GET /features`` reads
    the same table).
    """

    repository: FeatRepository

    cache_namespaces = FEAT_CACHE_NAMESPACES
    get_all_order_by = "name"

    def __init__(self, db: AsyncSession):
        """Set up the feat repository."""

        super().__init__(
            repository=FeatRepository(db),
            response_schema=FeatResponse,
            get_all_schema=FeatGetAllResponse,
        )

    async def create_feat(self, feat_data: FeatCreate) -> FeatResponse:
        """Create a feat (as a FEAT-source ``Feature``) after checking its name isn't already taken."""

        payload = feat_data.model_dump(exclude={"ability_score_increases"})

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

            if feat_data.ability_score_increases:
                increases = [
                    {"ability": inc.ability, "amount": inc.amount} for inc in feat_data.ability_score_increases
                ]
                await self.repository.set_ability_score_increases(item, increases, commit=False)

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
