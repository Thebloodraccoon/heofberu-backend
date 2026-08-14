"""Subclass CRUD service: cached catalog CRUD plus composed feature reads."""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.core.cache import use_cache
from app.features.classes.subclasses.base import SubclassScopedMixin
from app.features.classes.subclasses.cache import SUBCLASS_CACHE_NAMESPACES, invalidate_subclass_cache
from app.features.classes.subclasses.crud.repository import SubclassRepository
from app.features.classes.subclasses.crud.schemas import (
    SubclassBriefResponse,
    SubclassCreate,
    SubclassFullResponse,
    SubclassResponse,
    SubclassUpdate,
)
from app.features.shared.features.nested_service import NestedFeatureService
from app.models.subclass_model import Subclass


class SubclassCrudService(
    SubclassScopedMixin,
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
    the reads here go through the shared :class:`NestedFeatureService`.

    Writes purge the ``classes`` and ``nested_features`` cache namespaces
    via :func:`invalidate_subclass_cache` — the same namespaces
    ``ClassCrudService`` uses, since subclasses (and their features) are
    embedded in cached class responses.
    """

    repository: SubclassRepository

    cache_namespaces = SUBCLASS_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=SubclassRepository(db),
            response_schema=SubclassResponse,
        )
        self._features = NestedFeatureService(db)

    async def create_subclass(
        self, class_id: int, data: SubclassCreate, created_by_id: int | None = None
    ) -> SubclassResponse:
        """
        Create a subclass (and its nested features) for an existing class.
        Uses ``_atomic()`` so the subclass row and its features commit together.
        """

        payload = data.model_dump(exclude={"features"})
        payload["class_id"] = class_id
        payload["created_by_id"] = created_by_id

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

        await invalidate_subclass_cache()

        return await self._get_response(item.id)

    @use_cache()
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

    async def get_subclass(self, class_id: int, subclass_id: int) -> SubclassFullResponse:
        """Class-scoped variant of :meth:`get_by_id`: 404s if the subclass belongs to a different class."""

        await self._get_or_404_for_class(class_id, subclass_id)
        return await self.get_by_id(subclass_id)

    async def list_for_class(self, class_id: int) -> list[SubclassBriefResponse]:
        subclasses = await self.repository.list_for_class(class_id)
        return [SubclassBriefResponse.model_validate(s) for s in subclasses]

    async def list_with_features(self, class_id: int) -> list[SubclassFullResponse]:
        """
        Return every subclass of ``class_id`` with its own SUBCLASS-source
        features embedded — used by ``ClassCrudService.get_by_id`` to build
        ``ClassFullResponse.subclasses`` without reaching into this
        service's private ``_features`` attribute.

        Fetches every subclass's features concurrently rather than
        sequentially — see ``ClassCrudService.get_by_id`` for why.
        """

        subclasses = await self.repository.list_for_class(class_id)

        features_lists = await asyncio.gather(
            *[self._features.list_for_source(FeatureSourceType.SUBCLASS, subclass.id) for subclass in subclasses]
        )

        return [
            SubclassFullResponse.model_validate(
                {**SubclassResponse.model_validate(subclass).model_dump(), "features": features}
            )
            for subclass, features in zip(subclasses, features_lists, strict=True)
        ]

    async def update_subclass(self, class_id: int, subclass_id: int, data: SubclassUpdate) -> SubclassResponse:
        await self._get_or_404_for_class(class_id, subclass_id)
        return await self.update(subclass_id, data)

    async def delete_subclass(self, class_id: int, subclass_id: int) -> None:
        await self._get_or_404_for_class(class_id, subclass_id)
        await self.delete(subclass_id)
