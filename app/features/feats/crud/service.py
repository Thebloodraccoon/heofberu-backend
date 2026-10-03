"""Feat CRUD service: cached catalog CRUD over the unified Feature/Feat engine."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.core.base.service import BeforeUpdateHook
from app.core.exceptions import RecordNotFoundError
from app.features.feats.cache import FEAT_CACHE_NAMESPACES
from app.features.feats.crud.repository import FeatRepository
from app.features.feats.crud.schemas import FeatCreate, FeatGetAllResponse, FeatResponse, FeatUpdate
from app.features.feats.exceptions import FeatPrerequisiteIncompleteError
from app.models.features.feature_model import Feature

_PREREQUISITE_FIELDS = ("prerequisite_ability", "prerequisite_minimum_score")


class FeatCrudService(CachedService[Feature, FeatCreate, FeatUpdate, FeatResponse, FeatGetAllResponse]):
    """
    Feat catalog CRUD, built directly on ``Feature`` (``source_type=FEAT``).

    Listing and detail reads come from :class:`CachedService`; the repository
    scopes every query to FEAT-source rows, and the listing is a brief
    column select (``has_static_effects``/``has_choices`` are real columns).
    Updates and deletes only touch the bare row; the effect tree is loaded
    once, for the response. Every write purges ``feats`` and the shared
    ``features`` namespace (``GET /features`` reads the same table).
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
        """Create a feat (as a FEAT-source ``Feature``) together with its optional ASI options."""

        payload = feat_data.model_dump(exclude={"ability_score_increases"})

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

            if feat_data.ability_score_increases:
                increases = [
                    {"ability": inc.ability, "amount": inc.amount} for inc in feat_data.ability_score_increases
                ]
                await self.repository.set_ability_score_increases(item, increases, commit=False)

            await self._invalidate_cache()

        return await self._get_response(item.id)

    async def update(
        self, item_id: int, update_data: FeatUpdate, *, before_update: BeforeUpdateHook | None = None
    ) -> FeatResponse:
        """Partially update a feat's base fields (ASI options are managed through the effects endpoints)."""

        feat = await self._get_row_or_404(item_id)
        fields = update_data.model_dump(exclude_unset=True)
        if before_update:
            before_update(feat, fields)
        self._ensure_prerequisite_complete(feat, fields)

        await self.repository.update(feat, fields)
        await self._invalidate_cache()

        return await self._get_response(item_id)

    async def delete(self, item_id: int) -> bool:
        """Delete a feat, blocked while any character still holds it."""

        feat = await self._get_row_or_404(item_id)
        result = await self.repository.delete(feat)
        await self._invalidate_cache()

        return result

    async def ensure_exists(self, item_id: int) -> None:
        """Raise ``RecordNotFoundError`` unless ``item_id`` is a FEAT-source feature."""

        await self._exists_or_404(item_id)

    async def _get_row_or_404(self, item_id: int) -> Feature:
        """Fetch the bare FEAT row (no effect tree) or raise ``RecordNotFoundError``."""

        feat = await self.repository.get_row(item_id)
        if feat is None:
            raise RecordNotFoundError(model_name=self.repository.model.__name__, model_id=str(item_id))

        return feat

    @staticmethod
    def _ensure_prerequisite_complete(feat: Feature, fields: dict) -> None:
        """A PATCH touching the ability prerequisite must leave ability and minimum score both set or both empty."""

        if not any(name in fields for name in _PREREQUISITE_FIELDS):
            return

        ability, score = (fields.get(name, getattr(feat, name)) for name in _PREREQUISITE_FIELDS)
        if (ability is None) != (score is None):
            raise FeatPrerequisiteIncompleteError()
