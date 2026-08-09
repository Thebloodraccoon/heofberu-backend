"""Feature CRUD service with source_type/FK consistency re-validation."""

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base_service import BaseService, Page
from app.core.cache import use_cache
from app.features.features.exceptions import FeatureNotOwnedException, InvalidFeatureSourceException
from app.features.features.repository import FeatureRepository
from app.features.features.schemas import (
    _REQUIRED_FK_BY_SOURCE_TYPE,
    FeatureCreate,
    FeatureGetAllResponse,
    FeatureReplaceItem,
    FeatureResponse,
    FeatureUpdate,
    NestedFeatureCreate,
)
from app.models.feature_model import Feature


async def create_features_for_source(
    db: AsyncSession,
    source_type: FeatureSourceType,
    source_id: int,
    items: list[NestedFeatureCreate] | None,
    created_by_id: int | None,
    *,
    commit: bool = False,
) -> list[Feature]:
    """
    Create ``Feature`` rows attached to a source record inside an open transaction.

    Called by race/class/background/feat/subclass create services so a client
    can supply features up front in the same request that creates the source.

    Args:
        db: Active session — must already be inside the caller's
            ``_atomic()`` block so rows share the parent transaction.
        source_type: Which source the features belong to. Determines the FK
            column that gets set (CLASS→class_id, SUBCLASS→subclass_id, ...).
        source_id: ID of the owning record.
        items: Nested feature payloads. ``None`` or empty returns ``[]``.
        created_by_id: Optional GM id stored on each created feature.
        commit: Pass ``False`` when called from within ``_atomic()``.

    Returns:
        The created ``Feature`` model instances.
    """

    if not items:
        return []

    fk_name = _REQUIRED_FK_BY_SOURCE_TYPE[source_type]
    if fk_name is None:
        raise ValueError(f"source_type='{source_type.value}' has no source FK; nested creation is not supported.")

    repository = FeatureRepository(db)
    created: list[Feature] = []

    for item in items:
        payload = item.model_dump()
        payload["source_type"] = source_type
        payload[fk_name] = source_id
        feature = FeatureCreate(**payload)  # re-runs source_type/FK consistency validator
        created.append(await repository.create(feature.model_dump(), commit=commit))

    return created


async def replace_features_for_source(
    db: AsyncSession,
    source_type: FeatureSourceType,
    source_id: int,
    items: list[FeatureReplaceItem] | None,
    created_by_id: int | None,
    *,
    commit: bool = False,
) -> None:
    """
    Full-replace the features owned by a source record, matched by id.

    Every feature of the source is read; then:

    - items carrying an ``id`` update that feature in place — the row
      keeps its id, so ``character_features`` grants (and any player notes
      on them) survive;
    - items without an ``id`` create a new feature attached to the source;
    - existing features whose id is not in the payload are deleted, which
      cascades their ``character_features`` rows away.

    Called from the parent entity's service (race/class/background/feat/
    subclass) with ``commit=False`` inside its ``_atomic()`` block.

    Args:
        db: Active session — must already be inside the caller's
            ``_atomic()`` block so rows share the parent transaction.
        source_type: Which source the features belong to (CLASS, SUBCLASS,
            RACE, BACKGROUND, FEAT).
        source_id: ID of the owning record.
        items: Full replacement list of feature payloads. ``None`` or
            empty deletes all current features of the source.
        created_by_id: Optional GM id stored on newly created features.
        commit: Pass ``False`` when called from within ``_atomic()``.

    Raises:
        ValueError: ``source_type`` has no source FK (shouldn't happen —
            callers only pass source-bound types).
        FeatureNotOwnedException: an item's ``id`` does not belong to this
            source (400).
    """

    fk_name = _REQUIRED_FK_BY_SOURCE_TYPE[source_type]
    if fk_name is None:
        raise ValueError(f"source_type='{source_type.value}' has no source FK; replacement is not supported.")

    fk_attr = getattr(Feature, fk_name)

    result = await db.execute(select(Feature).where(fk_attr == source_id))
    existing = {feature.id: feature for feature in result.scalars().unique().all()}

    incoming = list(items or [])
    incoming_ids = {item.id for item in incoming if item.id is not None}

    # Every provided id must be owned by this source.
    for item in incoming:
        if item.id is not None and item.id not in existing:
            raise FeatureNotOwnedException(source_type.value, source_id, item.id)

    for item in incoming:
        if item.id is None:
            payload = item.model_dump(exclude={"id"})
            payload["source_type"] = source_type
            payload[fk_name] = source_id
            feature = FeatureCreate(**payload)  # re-runs source_type/FK consistency validator
            db.add(Feature(**feature.model_dump(), created_by_id=created_by_id))
        else:
            current = existing[item.id]
            current.name = item.name
            current.level = item.level
            current.description = item.description
            current.is_homebrew = item.is_homebrew

    for feature_id, _feature in existing.items():
        if feature_id not in incoming_ids:
            # Bulk delete (bypasses the ORM unit of work) so loaded
            # CharacterFeature grants are not nulled out by the session —
            # the DB-level ON DELETE CASCADE on features.id removes them.
            await db.execute(delete(Feature).where(Feature.id == feature_id))

    if commit:
        await db.commit()
    else:
        await db.flush()


class FeatureService(BaseService[Feature, FeatureCreate, FeatureUpdate, FeatureResponse, FeatureGetAllResponse]):
    """
    Feature-specific CRUD service built on :class:`BaseService`.

    Adds:
      - filtered listing by source_type/class_id/subclass_id/race_id/
        background_id/feat_id via the generic ``filters`` dict;
      - CRUD restricted to standalone (OTHER) features: class/race/
        background/feat/subclass features are owned by their parent
        record and are managed through that parent's nested ``features``
        payloads and the ``PUT /{source}/{id}/features`` replace
        endpoints, not through ``/features/``;
      - update restrictions: ``source_type`` and its FK are immutable, and
        ``level`` on a non-CLASS/SUBCLASS feature is rejected.

    Listing and detail reads are cached via ``@use_cache`` under the
    ``features`` namespace. The parent services (race/class/background/
    feat) invalidate this namespace too when their feature lists change.
    """

    repository: FeatureRepository

    cache_namespaces = ("features",)

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=FeatureRepository(db),
            response_schema=FeatureResponse,
            get_all_schema=FeatureGetAllResponse,
        )

    @use_cache()
    async def get_all(
        self,
        page: int = 1,
        size: int = 100,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
    ) -> Page[FeatureGetAllResponse]:
        """Cached lightweight listing — see ``BaseService.get_all``."""

        return await super().get_all(page=page, size=size, filters=filters, search=search)

    @use_cache()
    async def get_by_id(self, item_id: int) -> FeatureResponse:
        """Cached single-record fetch — see ``BaseService.get_by_id``."""

        return await super().get_by_id(item_id)

    def _require_standalone(self, feature: Feature) -> None:
        """Reject CRUD on a source-owned feature via ``/features/``."""

        if feature.source_type != FeatureSourceType.OTHER:
            raise InvalidFeatureSourceException(
                "Only standalone (OTHER) features can be managed through /features/; "
                "class/race/background/feat/subclass features are managed through their parent records."
            )

    async def update_feature(self, feature_id: int, update_data: FeatureUpdate) -> FeatureResponse:
        """
        Update a standalone (OTHER) feature.

        Source-owned features (class/race/background/feat/subclass) cannot
        be edited through ``/features/`` — use the parent's replace
        endpoint. ``source_type`` and its FK can't change — ownership is
        permanent. Only ``name``, ``level``, ``description`` and
        ``is_homebrew`` are editable. Setting a non-``None`` ``level`` on
        a feature that isn't CLASS/SUBCLASS is rejected with a 400 (level
        is only meaningful for class/subclass features).
        """

        feature = await self._get_or_404(feature_id)
        self._require_standalone(feature)
        fields = update_data.model_dump(exclude_unset=True)

        if (
            "level" in fields
            and fields["level"] is not None
            and feature.source_type not in (FeatureSourceType.CLASS, FeatureSourceType.SUBCLASS)
        ):
            raise InvalidFeatureSourceException("'level' is only meaningful when source_type is CLASS or SUBCLASS.")

        updated_feature = await self.repository.update(feature, fields)
        await self._invalidate_cache()

        return self.response_schema.model_validate(updated_feature)

    async def delete(self, feature_id: int) -> bool:
        """
        Delete a standalone (OTHER) feature, cascading away any
        ``CharacterFeature`` grants on it.

        Source-owned features are deleted through their parent's replace
        endpoint instead.
        """

        feature = await self._get_or_404(feature_id)

        self._require_standalone(feature)
        result = await self.repository.delete(feature)
        await self._invalidate_cache()

        return result
