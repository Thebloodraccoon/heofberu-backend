"""
Per-source (nested) feature service.

The race/class/background/feat/subclass catalogs no longer embed their
``features`` in the parent record responses. A parent's features are now
read and mutated through this service instead:

  - reads (``list_for_source``) are cached under the dedicated
    ``nested_features`` namespace — the per-source feature listing
    endpoints (``GET /{source}/{id}/features``) are served from it;
  - writes (add/update/remove) delegate to ``FeatureService``, which owns
    the row-level source-ownership logic.

Invalidation is *not* done inside the mutating methods here: they run
inside the caller's ``_atomic()`` transaction (``commit=False``), and
purging before commit would let a concurrent read repopulate the cache
with pre-commit rows. Instead the caller purges the ``nested_features``
namespace after the transaction commits:

  - ``SourceFeatureMixin._mutate_feature`` calls ``self._features.invalidate()``
    for feature-level writes;
  - the parent catalog services include ``"nested_features"`` in their
    ``cache_namespaces`` so their catalog-level create/update/delete
    (``BaseService._invalidate_cache``) purges it too.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.cache import invalidate, use_cache
from app.features.features.schemas import (
    _REQUIRED_FK_BY_SOURCE_TYPE,
    NestedFeatureCreate,
    NestedFeatureResponse,
)
from app.features.features.service import FeatureService
from app.models.feature_model import Feature


class NestedFeatureService:
    """
    Per-source feature reads and writes behind the ``nested_features`` cache
    namespace.

    The parent catalog services (race/class/background/feat) and the class
    service's subclass feature methods each hold one instance (``_features``)
    and expose it through their own ``add_feature``/``update_feature``/
    ``remove_feature``/``list_features`` methods.
    """

    cache_namespaces = ("nested_features",)

    def __init__(self, db: AsyncSession):
        self.db = db
        self._features = FeatureService(db)

    @use_cache()
    async def list_for_source(
        self, source_type: FeatureSourceType, source_id: int
    ) -> list[NestedFeatureResponse]:
        """
        Return every feature owned by ``source_id`` (ordered by id).

        Cached under the ``nested_features`` namespace; purged by any
        feature-level write and by catalog-level create/update/delete.
        """

        fk_name = _REQUIRED_FK_BY_SOURCE_TYPE[source_type]
        if fk_name is None:
            raise ValueError(
                f"source_type='{source_type.value}' has no source FK; "
                "per-source feature listing is not supported."
            )

        result = await self.db.execute(
            select(Feature)
            .where(getattr(Feature, fk_name) == source_id)
            .order_by(Feature.id)
        )
        return [NestedFeatureResponse.model_validate(feature) for feature in result.scalars().all()]

    async def create_feature_for_source(
        self,
        source_type: FeatureSourceType,
        source_id: int,
        item: NestedFeatureCreate,
        created_by_id: int | None,
        *,
        commit: bool = False,
    ) -> Feature:
        """Create a single source-owned feature row (see ``FeatureService``)."""

        return await self._features.create_feature_for_source(
            source_type, source_id, item, created_by_id, commit=commit
        )

    async def create_features_for_source(
        self,
        source_type: FeatureSourceType,
        source_id: int,
        items: list[NestedFeatureCreate] | None,
        created_by_id: int | None,
        *,
        commit: bool = False,
    ) -> list[Feature]:
        """Create several source-owned feature rows (see ``FeatureService``)."""

        return await self._features.create_features_for_source(
            source_type, source_id, items, created_by_id, commit=commit
        )

    async def update_feature_for_source(
        self,
        source_type: FeatureSourceType,
        source_id: int,
        feature_id: int,
        fields: dict[str, Any],
        *,
        commit: bool = False,
    ) -> Feature:
        """Update one source-owned feature in place (see ``FeatureService``)."""

        return await self._features.update_feature_for_source(
            source_type, source_id, feature_id, fields, commit=commit
        )

    async def delete_feature_for_source(
        self,
        source_type: FeatureSourceType,
        source_id: int,
        feature_id: int,
        *,
        commit: bool = False,
    ) -> None:
        """Delete one source-owned feature, cascading its grants away (see ``FeatureService``)."""

        await self._features.delete_feature_for_source(source_type, source_id, feature_id, commit=commit)

    async def invalidate(self) -> None:
        """Purge every cached per-source feature listing."""

        for namespace in self.cache_namespaces:
            await invalidate(namespace)
