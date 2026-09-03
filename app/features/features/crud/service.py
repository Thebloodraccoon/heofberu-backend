"""Feature CRUD service: the one central owner of every feature write and read."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import FeatureSourceType
from app.core.base.cached_service import CachedService
from app.core.cache import invalidate
from app.features.characters.progression.feature_sync import reconcile_characters_for_source
from app.features.features.cache import FEATURE_CACHE_NAMESPACES, invalidate_feature_cache
from app.features.features.crud.repository import FeatureRepository
from app.features.features.crud.schemas import (
    _FEATURE_LEVEL_MAX,
    _FEATURE_LEVEL_MIN,
    _REQUIRED_FK_BY_SOURCE_TYPE,
    FeatureCreate,
    FeatureGetAllResponse,
    FeatureResponse,
    FeatureUpdate,
    NestedFeatureCreate,
    NestedFeatureResponse,
)
from app.features.features.exceptions import InvalidFeatureSourceException
from app.models.feature_model import Feature

# The per-catalog cache namespace holding that catalog's own feature list.
# A central feature write purges the owning catalog's list namespace (and
# only that one) so its cached ``GET /{source}/features`` goes stale.
SOURCE_FEATURE_LIST_NAMESPACE: dict[FeatureSourceType, str | None] = {
    FeatureSourceType.CLASS: "class_features",
    FeatureSourceType.SUBCLASS: "subclass_features",
    FeatureSourceType.RACE: "race_features",
    FeatureSourceType.SUBRACE: "subrace_features",
    FeatureSourceType.BACKGROUND: "background_features",
    FeatureSourceType.OTHER: None,
}

# The parent catalog read namespace holding that source's cached FULL response.
# A central feature write must also purge it: the parent detail reads embed
# their features, so the whole cached payload would go stale otherwise.
# Subrace detail is cached under ``races`` and subclass detail under ``classes``.
SOURCE_PARENT_READ_NAMESPACE: dict[FeatureSourceType, str | None] = {
    FeatureSourceType.CLASS: "classes",
    FeatureSourceType.SUBCLASS: "classes",
    FeatureSourceType.RACE: "races",
    FeatureSourceType.SUBRACE: "races",
    FeatureSourceType.BACKGROUND: "backgrounds",
    FeatureSourceType.OTHER: None,
}


def _get_fk_name(source_type: FeatureSourceType) -> str:
    """The source-FK column for ``source_type`` (raises for OTHER)."""

    fk_name = _REQUIRED_FK_BY_SOURCE_TYPE[source_type]
    if fk_name is None:
        raise ValueError(
            f"source_type='{source_type.value}' has no source FK; per-source feature management is not supported."
        )

    return fk_name


class FeatureCrudService(CachedService[Feature, FeatureCreate, FeatureUpdate, FeatureResponse, FeatureGetAllResponse]):
    """
    The single feature service: every feature — standalone (OTHER) or owned by
    a class/subclass/race/subrace/background — is created, read, updated and
    deleted through this one class.

    ``list_for_source`` is an uncached read; the parent catalogs cache their
    own feature lists and a feature write here invalidates the owning
    catalog's lists via :data:`SOURCE_FEATURE_LIST_NAMESPACE`, its read
    namespace via :data:`SOURCE_PARENT_READ_NAMESPACE`, and the shared
    ``features`` namespace. ``create_feature_for_source``/
    ``create_features_for_source`` run inside the caller's ``_atomic()``
    transaction (``commit=False``). Source-owned feature writes also
    reconcile affected characters' auto-granted ``character_features`` in the
    same transaction via ``reconcile_characters_for_source``.
    """

    repository: FeatureRepository

    cache_namespaces = FEATURE_CACHE_NAMESPACES
    get_all_order_by = "name"

    def __init__(self, db: AsyncSession):
        """Initialize the service with the feature repository."""

        super().__init__(
            repository=FeatureRepository(db),
            response_schema=FeatureResponse,
            get_all_schema=FeatureGetAllResponse,
        )

    async def _purge_feature_cache(self, source_type: FeatureSourceType) -> None:
        """
        Purge every cached read a feature write can hit.

        Clears the shared ``features`` namespace, plus (for source-owned
        features) the owning catalog's feature-list and read namespaces.
        """

        await invalidate_feature_cache()

        list_namespace = SOURCE_FEATURE_LIST_NAMESPACE[source_type]
        if list_namespace is not None:
            await invalidate(list_namespace)

        parent_namespace = SOURCE_PARENT_READ_NAMESPACE[source_type]
        if parent_namespace is not None:
            await invalidate(parent_namespace)

    async def list_for_source(self, source_type: FeatureSourceType, source_id: int) -> list[NestedFeatureResponse]:
        """
        Return every ``Feature`` row owned by ``source_id`` (ordered by id).

        Uncached on purpose: parent catalogs cache their own feature lists
        under dedicated namespaces, so caching here would double-cache.
        Raises ``ValueError`` when ``source_type`` is OTHER (no source FK).
        """

        fk_name = _get_fk_name(source_type)
        result = await self.repository.db.execute(
            select(Feature)
            .where(getattr(Feature, fk_name) == source_id)
            .options(selectinload(Feature.ability_increases))
            .order_by(Feature.id)
        )
        rows = result.scalars().all()
        return [NestedFeatureResponse.model_validate(row) for row in rows]

    def _source_fk_value(self, source_type: FeatureSourceType, item: FeatureCreate | Feature) -> int | None:
        """The owning source's id for a feature (``None`` for OTHER-only features)."""

        if source_type is FeatureSourceType.OTHER:
            return None

        return getattr(item, _get_fk_name(source_type))

    async def _reconcile_characters(self, source_type: FeatureSourceType, source_id: int | None) -> None:
        """
        Reconcile auto-granted character features after a source-owned feature write.

        Runs in the caller's open transaction (never commits here); OTHER
        features are never auto-granted, so they need no reconciliation.
        """

        if source_id is None:
            return

        await reconcile_characters_for_source(self.repository.db, source_type, source_id)

    async def create(self, create_data: FeatureCreate) -> FeatureResponse:
        """
        Create a feature of any source type.

        The ``FeatureCreate`` validator pins the source FK and enforces the
        level rules; a source-owned feature is granted to the owning
        record's characters in the same transaction.
        """

        item = await self.repository.create(create_data.model_dump(), commit=False)
        await self._reconcile_characters(
            create_data.source_type, self._source_fk_value(create_data.source_type, create_data)
        )
        await self.repository.commit_or_flush()
        # The commit expires the row; refetch with eager loads so serialization
        # never trips an async lazy load on the empty ``ability_increases`` collection.
        item = await self.repository.get_by_id(item.id)
        await self._purge_feature_cache(create_data.source_type)

        return self.response_schema.model_validate(item)

    async def create_features_for_source(
        self,
        source_type: FeatureSourceType,
        source_id: int,
        items: list[NestedFeatureCreate] | None,
        *,
        commit: bool = False,
    ) -> list[Feature]:
        """Create ``Feature`` rows attached to a source record inside an open transaction."""

        if not items:
            return []

        created: list[Feature] = []

        for item in items:
            created.append(
                await self.create_feature_for_source(
                    source_type,
                    source_id,
                    item,
                    commit=commit,
                )
            )

        return created

    async def create_feature_for_source(
        self,
        source_type: FeatureSourceType,
        source_id: int,
        item: NestedFeatureCreate,
        *,
        commit: bool = False,
    ) -> Feature:
        """
        Create a single ``Feature`` row attached to a source record.

        No cache invalidation happens here — the caller owns its transaction
        and purges its own namespaces after commit.
        """

        fk_name = _get_fk_name(source_type)
        payload = item.model_dump()
        payload["source_type"] = source_type
        payload[fk_name] = source_id
        feature = FeatureCreate(**payload)  # re-runs source_type/FK/level consistency validator

        return await self.repository.create(feature.model_dump(), commit=commit)

    def _validate_level_update(self, feature: Feature, fields: dict) -> None:
        """Reject ``level`` patches that would break the level rules."""

        if "level" not in fields:
            return

        level = fields["level"]

        if level is None and feature.source_type in (
            FeatureSourceType.CLASS,
            FeatureSourceType.SUBCLASS,
        ):
            raise InvalidFeatureSourceException(
                "CLASS/SUBCLASS features require 'level' — it can only be changed, not cleared."
            )

        if feature.source_type in (FeatureSourceType.CLASS, FeatureSourceType.SUBCLASS) and not (
            _FEATURE_LEVEL_MIN <= level <= _FEATURE_LEVEL_MAX
        ):
            raise InvalidFeatureSourceException(
                f"'level' for CLASS/SUBCLASS features must be between {_FEATURE_LEVEL_MIN} and {_FEATURE_LEVEL_MAX}."
            )

    async def update_feature(self, feature_id: int, update_data: FeatureUpdate) -> FeatureResponse:
        """
        Update a feature of any source type, keeping its id.

        ``source_type`` and its FK can't change — ownership is permanent.
        A CLASS/SUBCLASS feature's ``level`` is mandatory (1-20) and may be
        changed but never cleared. Any edit re-reconciles the owning record's
        characters in the same transaction.
        """

        feature = await self._get_or_404(feature_id)
        fields = update_data.model_dump(exclude_unset=True)

        self._validate_level_update(feature, fields)

        source_type = feature.source_type
        source_id = self._source_fk_value(source_type, feature)

        for field, value in fields.items():
            setattr(feature, field, value)

        await self._reconcile_characters(source_type, source_id)
        await self.repository.commit_or_flush()
        await self._purge_feature_cache(source_type)

        # Re-fetch after the commit so the expired row's ``ability_increases``
        # are eagerly loaded before serialization (async-safe).
        feature = await self.repository.get_by_id(feature_id)
        return self.response_schema.model_validate(feature)

    async def delete(self, feature_id: int) -> bool:
        """
        Delete a feature of any source type, cascading away any
        ``CharacterFeature`` grants and refreshing affected characters.
        """

        feature = await self._get_or_404(feature_id)
        source_type = feature.source_type
        source_id = self._source_fk_value(source_type, feature)

        result = await self.repository.delete(feature)
        await self._reconcile_characters(source_type, source_id)
        await self.repository.commit_or_flush()
        await self._purge_feature_cache(source_type)

        return result
