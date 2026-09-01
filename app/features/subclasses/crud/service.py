"""Subclass CRUD service: cached catalog CRUD plus composed feature reads."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.core.cache import use_cache
from app.core.cache.client import cache_prefix
from app.core.exceptions import RecordNotFoundError
from app.features.classes.crud.repository import ClassRepository
from app.features.subclasses.cache import SUBCLASS_CACHE_NAMESPACES, invalidate_subclass_cache
from app.features.subclasses.crud.repository import SubclassRepository
from app.features.subclasses.crud.schemas import (
    SubclassBriefResponse,
    SubclassCreate,
    SubclassFullResponse,
    SubclassResponse,
    SubclassUpdate,
)
from app.features.features.crud.service import FeatureCrudService
from app.models.subclass_model import Subclass


class SubclassCrudService(
    BaseService[Subclass, SubclassCreate, SubclassUpdate, SubclassResponse, None],
):
    """
    Subclass catalog CRUD built on :class:`BaseService`.

    Extends the base with class-scoped 404s, atomic creation of the
    subclass row, and a ``get_by_id`` that returns the subclass with its
    own SUBCLASS-source ``features``. Reads go through the central
    :class:`FeatureCrudService`; per-subclass feature writes live in
    ``features/``. Writes purge ``SUBCLASS_CACHE_NAMESPACES``.
    """

    repository: SubclassRepository

    cache_namespaces = SUBCLASS_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize the service with its repositories and the central feature catalog."""

        super().__init__(
            repository=SubclassRepository(db),
            response_schema=SubclassResponse,
        )
        self._features = FeatureCrudService(db)
        self._class_repository = ClassRepository(db)

    async def create_subclass(self, data: SubclassCreate) -> SubclassResponse:
        """Create a subclass for an existing class, atomically with its nested features."""

        await self._ensure_class_exists(data.class_id)
        payload = data.model_dump(exclude={"features"})

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

        await invalidate_subclass_cache()

        return await self._get_response(item.id)

    @use_cache(key_builder=lambda self, item_id: f"{cache_prefix()}:classes:subclass:get_by_id:{item_id}")
    async def get_by_id(self, item_id: int) -> SubclassFullResponse:
        """
        Return the subclass plus its own SUBCLASS-source ``features``.

        Cached under the ``classes`` namespace — every write in this
        subdomain purges it via :func:`invalidate_subclass_cache`.
        """

        subclass = await self._get_or_404(item_id)
        features = await self._features.list_for_source(FeatureSourceType.SUBCLASS, item_id)

        return SubclassFullResponse.model_validate(
            {**SubclassResponse.model_validate(subclass).model_dump(), "features": features}
        )

    async def get_subclass(self, subclass_id: int) -> SubclassFullResponse:
        """Return a subclass's full picture, 404ing if it belongs to a different class."""

        return await self.get_by_id(subclass_id)

    async def list_for_class(self, class_id: int) -> list[SubclassBriefResponse]:
        """Return all subclasses for ``class_id`` as brief rows."""

        subclasses = await self.repository.list_for_class(class_id)
        return [SubclassBriefResponse.model_validate(s) for s in subclasses]

    async def _ensure_class_exists(self, class_id: int) -> None:
        """Raise ``RecordNotFoundError`` when no class with ``class_id`` exists."""

        if not await self._class_repository.exists_by_id(class_id):
            raise RecordNotFoundError(model_name="Class", model_id=str(class_id))
