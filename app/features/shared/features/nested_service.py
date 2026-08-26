"""
Per-source (nested) feature service.

The race/subrace/class/background/feat/subclass catalogs no longer embed
their ``features`` in the parent record responses. A parent's features are
now read and mutated through this service instead:

  - reads (``list_for_source``) are cached under the dedicated
    ``nested_features`` namespace, via ``NestedCollectionService`` — the
    per-source feature listing endpoints (``GET /{source}/{id}/features``)
    are served from it;
  - writes (add/update/remove) delegate to ``FeatureCrudService``, which owns
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

from app.constants import FeatureSourceType
from app.core.base.nested_service import NestedCollectionService
from app.features.features.crud.service import FeatureCrudService
from app.features.shared.features.schemas import (
    _REQUIRED_FK_BY_SOURCE_TYPE,
    NestedFeatureCreate,
    NestedFeatureResponse,
)
from app.models.feature_model import Feature


class NestedFeatureService(NestedCollectionService[Feature, NestedFeatureResponse]):
    """
    Per-source feature reads and writes behind the ``nested_features`` cache
    namespace.

    The parent catalog services (race/subrace/class/background) and
    the class service's subclass feature methods each hold one instance
    (``_features``) and expose it through their own ``add_feature``/
    ``update_feature``/``remove_feature``/``list_features`` methods.

    Reads (``list_for_source``) and namespace ``invalidate()`` come from
    ``NestedCollectionService``; only ``fk_for`` and the write methods
    (delegating to ``FeatureCrudService``, which owns row-level ownership
    rules) are declared here.
    """

    model = Feature
    response_schema = NestedFeatureResponse
    cache_namespaces = ("nested_features",)

    def __init__(self, db):
        super().__init__(db)
        self._features = FeatureCrudService(db)

    def fk_for(self, source_type: FeatureSourceType) -> str:
        """Resolve the FK column for ``source_type``, or raise if unsupported."""

        fk_name = _REQUIRED_FK_BY_SOURCE_TYPE[source_type]
        if fk_name is None:
            raise ValueError(
                f"source_type='{source_type.value}' has no source FK; per-source feature listing is not supported."
            )
        return fk_name

    async def create_feature_for_source(
        self,
        source_type: FeatureSourceType,
        source_id: int,
        item: NestedFeatureCreate,
        *,
        commit: bool = False,
    ) -> Feature:
        """Create a single source-owned feature row (see ``FeatureCrudService``)."""

        return await self._features.create_feature_for_source(source_type, source_id, item, commit=commit)

    async def create_features_for_source(
        self,
        source_type: FeatureSourceType,
        source_id: int,
        items: list[NestedFeatureCreate] | None,
        *,
        commit: bool = False,
    ) -> list[Feature]:
        """Create several source-owned feature rows (see ``FeatureCrudService``)."""

        return await self._features.create_features_for_source(source_type, source_id, items, commit=commit)

    async def update_feature_for_source(
        self,
        source_type: FeatureSourceType,
        source_id: int,
        feature_id: int,
        fields: dict[str, Any],
        *,
        commit: bool = False,
    ) -> Feature:
        """Update one source-owned feature in place (see ``FeatureCrudService``)."""

        return await self._features.update_feature_for_source(source_type, source_id, feature_id, fields, commit=commit)

    async def delete_feature_for_source(
        self,
        source_type: FeatureSourceType,
        source_id: int,
        feature_id: int,
        *,
        commit: bool = False,
    ) -> None:
        """Delete one source-owned feature, cascading its grants away (see ``FeatureCrudService``)."""

        await self._features.delete_feature_for_source(source_type, source_id, feature_id, commit=commit)
