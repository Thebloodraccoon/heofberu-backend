"""
Generic base for "per-source nested collection" services: a cached,
FK-scoped listing plus namespace invalidation.

Both ``NestedFeatureService`` (app/features/shared/features/nested_service.py)
and ``NestedSourceItemService`` (app/features/shared/items/nested_service.py) are
this same shape:

    SELECT <Model> WHERE <fk> == source_id ORDER BY id  -->  cached list

Writes are NOT generalized here — they differ too much per domain
(``NestedSourceItemService`` inserts/deletes ``SourceItem`` rows directly;
``NestedFeatureService`` delegates to ``FeatureCrudService`` for
ownership-aware writes, since features have row-level ownership rules
nested items don't). Only the read + cache-namespace boilerplate is
shared, since that part is byte-for-byte identical across both today.
"""

from typing import Any, Generic

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import TypeVar

from app.core.cache import invalidate, use_cache

Model = TypeVar("Model")
ResponseSchema = TypeVar("ResponseSchema")
SourceType = TypeVar("SourceType")


class NestedCollectionService(Generic[Model, ResponseSchema]):
    """
    Cached ``SELECT * FROM <model> WHERE <fk> = source_id ORDER BY id``,
    behind a single cache namespace.

    Subclasses set:
      - ``model``: the SQLAlchemy model to select from.
      - ``response_schema``: schema each row is validated into.
      - ``cache_namespaces``: passed through unchanged to ``use_cache``/
        ``invalidate`` — kept as a tuple (not a single string) because
        that's the shape ``BaseService.cache_namespaces`` already uses
        everywhere else.
      - ``fk_for(source_type)``: resolves the polymorphic FK column name
        for a given source type (``"race_id"``, ``"background_id"``, ...).
        Raise inside it (rather than returning ``None``) for source types
        that don't support this listing — see
        ``NestedFeatureService.fk_for``.
      - optional ``load_options``: extra ``.options(...)`` for the select
        (e.g. ``NestedSourceItemService`` needs ``selectinload(item)``).

    Example::

        class NestedFeatureService(NestedCollectionService[Feature, NestedFeatureResponse]):
            model = Feature
            response_schema = NestedFeatureResponse
            cache_namespaces = ("nested_features",)

            def fk_for(self, source_type: FeatureSourceType) -> str:
                fk_name = _REQUIRED_FK_BY_SOURCE_TYPE[source_type]
                if fk_name is None:
                    raise ValueError(...)
                return fk_name

            # writes stay domain-specific, defined alongside this class
    """

    model: type[Model]
    response_schema: type[ResponseSchema]
    cache_namespaces: tuple[str, ...]
    load_options: tuple[Any, ...] = ()

    def __init__(self, db: AsyncSession):
        self.db = db

    def fk_for(self, source_type: SourceType) -> str:
        """Resolve the polymorphic FK column name for ``source_type``."""

        raise NotImplementedError

    @use_cache()
    async def list_for_source(self, source_type: SourceType, source_id: int) -> list[ResponseSchema]:
        """
        Return every row owned by ``source_id`` (ordered by id).

        Cached under ``cache_namespaces``; purged by :meth:`invalidate`.
        """

        fk_name = self.fk_for(source_type)

        query = select(self.model).where(getattr(self.model, fk_name) == source_id).order_by(self.model.id)
        if self.load_options:
            query = query.options(*self.load_options)

        result = await self.db.execute(query)
        rows = result.scalars().unique().all() if self.load_options else result.scalars().all()
        return [self.response_schema.model_validate(row) for row in rows]

    async def invalidate(self) -> None:
        """Purge every cached listing under this service's namespaces."""

        for namespace in self.cache_namespaces:
            await invalidate(namespace)
