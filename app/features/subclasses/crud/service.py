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

    Extends the generic base with:
      - class-scoped 404s (``SubclassNotFoundException`` instead of the
        base ``RecordNotFoundError``, and belonging to the right
        ``class_id``) via :class:`SubclassScopedMixin`;
      - atomic creation of the subclass row alongside its nested
        SUBCLASS-source features;
      - ``get_by_id`` overridden to return the full picture
        (``SubclassFullResponse``): base fields plus its own
        SUBCLASS-source ``features``.

    Per-subclass feature writes (add/update/remove) live in
    :class:`SubclassFeatureService` (the ``features/`` subpackage);
    the reads here go through the central :class:`FeatureCrudService`.

    Writes purge the ``classes``, ``subclass_features`` and ``features``
    cache namespaces via :func:`invalidate_subclass_cache` — a superset of
    what ``ClassCrudService`` uses, since subclasses (and their features)
    are embedded in cached class responses.
    """

    repository: SubclassRepository

    cache_namespaces = SUBCLASS_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=SubclassRepository(db),
            response_schema=SubclassResponse,
        )
        self._features = FeatureCrudService(db)
        self._class_repository = ClassRepository(db)

    async def create_subclass(self, data: SubclassCreate) -> SubclassResponse:
        """
        Create a subclass (and its nested features) for an existing class.
        Uses ``_atomic()`` so the subclass row and its features commit together.
        """

        await self._ensure_class_exists(data.class_id)
        payload = data.model_dump(exclude={"features"})

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

        await invalidate_subclass_cache()

        return await self._get_response(item.id)

    @use_cache(key_builder=lambda self, item_id: f"{cache_prefix()}:classes:subclass:get_by_id:{item_id}")
    async def get_by_id(self, item_id: int) -> SubclassFullResponse:
        """
        Return a subclass with its own SUBCLASS-source ``features``
        included — overrides ``BaseService.get_by_id`` (bare
        ``SubclassResponse``) the same way ``ClassCrudService.get_by_id``
        overrides its base to return the full picture.

        Cached under the ``classes`` namespace — every write in this
        subdomain purges it via :func:`invalidate_subclass_cache`, so a
        feature or base-field write on this subclass invalidates this
        cached read too.
        """

        subclass = await self._get_or_404(item_id)
        features = await self._features.list_for_source(FeatureSourceType.SUBCLASS, item_id)

        return SubclassFullResponse.model_validate(
            {**SubclassResponse.model_validate(subclass).model_dump(), "features": features}
        )

    async def get_subclass(self, subclass_id: int) -> SubclassFullResponse:
        """Class-scoped variant of :meth:`get_by_id`: 404s if the subclass belongs to a different class."""

        return await self.get_by_id(subclass_id)

    async def list_for_class(self, class_id: int) -> list[SubclassBriefResponse]:
        subclasses = await self.repository.list_for_class(class_id)
        return [SubclassBriefResponse.model_validate(s) for s in subclasses]

    async def _ensure_class_exists(self, class_id: int) -> None:
        """
        Raise ``RecordNotFoundError`` when no class with ``class_id`` exists.

        Used by operations that don't target an existing subrace row yet
        (create/list) so a missing class 404s exactly as it did before the
        subdomain split.
        """

        if not await self._class_repository.exists_by_id(class_id):
            raise RecordNotFoundError(model_name="Class", model_id=str(class_id))
