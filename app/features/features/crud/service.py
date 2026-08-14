"""Feature CRUD service: standalone CRUD plus per-source feature management."""

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.cached_service import CachedService
from app.features.features.cache import FEATURE_CACHE_NAMESPACES, invalidate_feature_cache
from app.features.features.crud.repository import FeatureRepository
from app.features.features.crud.schemas import (
    FeatureCreate,
    FeatureGetAllResponse,
    FeatureResponse,
)
from app.features.features.exceptions import (
    FeatureNotFoundException,
    FeatureNotOwnedException,
    InvalidFeatureSourceException,
)
from app.features.shared.features.schemas import (
    _REQUIRED_FK_BY_SOURCE_TYPE,
    FeatureUpdate,
    NestedFeatureCreate,
)
from app.models.feature_model import Feature


def _get_fk_name(source_type: FeatureSourceType) -> str:
    """The source-FK column for ``source_type`` (raises for OTHER)."""

    fk_name = _REQUIRED_FK_BY_SOURCE_TYPE[source_type]
    if fk_name is None:
        raise ValueError(
            f"source_type='{source_type.value}' has no source FK; per-source feature management is not supported."
        )

    return fk_name


async def _get_source_feature(
    db: AsyncSession,
    source_type: FeatureSourceType,
    source_id: int,
    feature_id: int,
) -> Feature:
    """
    Fetch a feature by id and verify it is owned by ``source_id``.

    Raises:
        FeatureNotFoundException: no feature exists with ``feature_id``
            (404).
        FeatureNotOwnedException: the feature exists but belongs to a
            different source record (400).
    """

    fk_name = _get_fk_name(source_type)
    result = await db.execute(select(Feature).where(Feature.id == feature_id))
    feature = result.scalar_one_or_none()

    if feature is None:
        raise FeatureNotFoundException(feature_id)

    if getattr(feature, fk_name) != source_id:
        raise FeatureNotOwnedException(source_type.value, source_id, feature_id)

    return feature


class FeatureCrudService(CachedService[Feature, FeatureCreate, FeatureUpdate, FeatureResponse, FeatureGetAllResponse]):
    """
    Feature-specific CRUD service built on :class:`CachedService`.

    Encapsulates every feature operation in one place:

    - per-source management (``create_feature_for_source``,
      ``create_features_for_source``, ``update_feature_for_source``,
      ``delete_feature_for_source``) — used by the race/subrace/class/
      background/feat services and their per-feature endpoints;
    - standalone (OTHER) CRUD served by ``/features/`` — listing is pinned
      to OTHER, ``get_by_id`` only returns OTHER features, and create/
      update/delete reject source-owned features;
    - update restrictions: ``source_type`` and its FK are immutable, and
      ``level`` on a non-CLASS/SUBCLASS/OTHER feature is rejected.

    Listing and detail reads are cached via ``@use_cache`` under the
    ``features`` namespace. The parent services (race/subrace/class/
    background/feat) invalidate this namespace too when their feature
    lists change.
    """

    repository: FeatureRepository

    cache_namespaces = FEATURE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=FeatureRepository(db),
            response_schema=FeatureResponse,
            get_all_schema=FeatureGetAllResponse,
        )

    async def get_standalone(self, feature_id: int) -> FeatureResponse:
        """
        Fetch a single feature, but only standalone (OTHER) ones.

        Source-owned features (class/subclass/race/subrace/background/feat)
        are managed through their parent record and are not served by
        ``/features/`` — a request for one returns 404, as if it did not
        exist through this endpoint.
        """

        feature = await self.get_by_id(feature_id)
        if feature.source_type != FeatureSourceType.OTHER:
            raise FeatureNotFoundException(feature_id)

        return feature

    def _require_standalone(self, feature: Feature) -> None:
        """Reject CRUD on a source-owned feature via ``/features/``."""

        if feature.source_type != FeatureSourceType.OTHER:
            raise InvalidFeatureSourceException(
                "Only standalone (OTHER) features can be managed through /features/; "
                "class/subclass/race/subrace/background/feat features are managed through their parent records."
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
        """
        Create ``Feature`` rows attached to a source record inside an open transaction.

        Called by race/subrace/class/background/feat/subclass create
        services so a client can supply features up front in the same
        request that creates the source.

        Args:
            source_type: Which source the features belong to. Determines the
                FK column that gets set (CLASS→class_id, SUBCLASS→subclass_id,
                ...).
            source_id: ID of the owning record.
            items: Nested feature payloads. ``None`` or empty returns ``[]``.
            created_by_id: Optional GM id stored on each created feature.
            commit: Pass ``False`` when called from within the caller's
                ``_atomic()`` block so rows share the parent transaction.

        Returns:
            The created ``Feature`` model instances.
        """

        if not items:
            return []

        created: list[Feature] = []

        for item in items:
            created.append(
                await self.create_feature_for_source(
                    source_type,
                    source_id,
                    item,
                    created_by_id,
                    commit=commit,
                )
            )

        return created

    async def create_feature_for_source(
        self,
        source_type: FeatureSourceType,
        source_id: int,
        item: NestedFeatureCreate,
        created_by_id: int | None,
        *,
        commit: bool = False,
    ) -> Feature:
        """
        Create a single ``Feature`` row attached to a source record.

        Used by the per-feature add endpoints (``POST /{source}/{id}/features``)
        and by :meth:`create_features_for_source` (nested create payloads).

        Args:
            source_type: Which source the feature belongs to.
            source_id: ID of the owning record.
            item: The feature payload (name/description/level).
            created_by_id: Optional GM id stored on the created feature.
            commit: Pass ``False`` when called from within the caller's
                ``_atomic()`` block.

        Returns:
            The created ``Feature`` model instance.
        """

        fk_name = _get_fk_name(source_type)
        payload = item.model_dump()
        payload["source_type"] = source_type
        payload[fk_name] = source_id
        feature = FeatureCreate(**payload)  # re-runs source_type/FK consistency validator

        return await self.repository.create(feature.model_dump(), commit=commit)

    async def update_feature_for_source(
        self,
        source_type: FeatureSourceType,
        source_id: int,
        feature_id: int,
        fields: dict[str, Any],
        *,
        commit: bool = False,
    ) -> Feature:
        """
        Update one source-owned feature in place, keeping its id.

        Only ``name``, ``level`` and ``description`` are
        editable (``FeatureUpdate`` forbids anything else). Because the row
        keeps its id, ``character_features`` grants and any player notes on
        them survive. Setting a non-``None`` ``level`` on a non-CLASS/
        SUBCLASS/OTHER feature is rejected.

        Args:
            source_type: Which source the feature belongs to.
            source_id: ID of the owning record.
            feature_id: ID of the feature to update.
            fields: ``FeatureUpdate``-validated partial fields (exclude_unset).
            commit: Pass ``False`` when called from within the caller's
                ``_atomic()`` block.

        Raises:
            FeatureNotFoundException: no feature exists with ``feature_id``.
            FeatureNotOwnedException: the feature belongs to a different source.
            InvalidFeatureSourceException: ``level`` set on a source type where
                it is meaningless.
        """

        feature = await _get_source_feature(self.repository.db, source_type, source_id, feature_id)

        if (
            "level" in fields
            and fields["level"] is not None
            and source_type not in (FeatureSourceType.CLASS, FeatureSourceType.SUBCLASS, FeatureSourceType.OTHER)
        ):
            raise InvalidFeatureSourceException(
                "'level' is only meaningful when source_type is CLASS, SUBCLASS or OTHER."
            )

        for field, value in fields.items():
            setattr(feature, field, value)

        if commit:
            await self.repository.db.commit()
        else:
            await self.repository.db.flush()

        return feature

    async def delete_feature_for_source(
        self,
        source_type: FeatureSourceType,
        source_id: int,
        feature_id: int,
        *,
        commit: bool = False,
    ) -> None:
        """
        Delete one source-owned feature, cascading its ``character_features``
        grants away.

        Uses a bulk delete (bypassing the ORM unit of work) so any loaded
        ``CharacterFeature`` grants are not nulled out by the session — the
        DB-level ON DELETE CASCADE on ``features.id`` removes them.

        Args:
            source_type: Which source the feature belongs to.
            source_id: ID of the owning record.
            feature_id: ID of the feature to delete.
            commit: Pass ``False`` when called from within the caller's
                ``_atomic()`` block.

        Raises:
            FeatureNotFoundException: no feature exists with ``feature_id``.
            FeatureNotOwnedException: the feature belongs to a different source.
        """

        await _get_source_feature(self.repository.db, source_type, source_id, feature_id)
        await self.repository.db.execute(delete(Feature).where(Feature.id == feature_id))

        if commit:
            await self.repository.db.commit()
        else:
            await self.repository.db.flush()

    async def update_feature(self, feature_id: int, update_data: FeatureUpdate) -> FeatureResponse:
        """
        Update a standalone (OTHER) feature.

        Source-owned features (class/race/background/feat/subclass) cannot
        be edited through ``/features/`` — use the parent's per-feature
        endpoints. ``source_type`` and its FK can't change — ownership is
        permanent. Only ``name``, ``level`` and ``description`` are
        editable. Setting a non-``None`` ``level`` on
        a feature that isn't CLASS/SUBCLASS/OTHER is rejected with a 400
        (level is only meaningful for class, subclass and standalone
        features).
        """

        feature = await self._get_or_404(feature_id)
        self._require_standalone(feature)
        fields = update_data.model_dump(exclude_unset=True)

        if (
            "level" in fields
            and fields["level"] is not None
            and feature.source_type
            not in (
                FeatureSourceType.CLASS,
                FeatureSourceType.SUBCLASS,
                FeatureSourceType.OTHER,
            )
        ):
            raise InvalidFeatureSourceException(
                "'level' is only meaningful when source_type is CLASS, SUBCLASS or OTHER."
            )

        updated_feature = await self.repository.update(feature, fields)
        await invalidate_feature_cache()

        return self.response_schema.model_validate(updated_feature)

    async def delete(self, feature_id: int) -> bool:
        """
        Delete a standalone (OTHER) feature, cascading away any
        ``CharacterFeature`` grants on it.

        Source-owned features are deleted through their parent's per-feature
        endpoints instead.
        """

        feature = await self._get_or_404(feature_id)

        self._require_standalone(feature)
        result = await self.repository.delete(feature)
        await invalidate_feature_cache()

        return result
