"""Feature CRUD service: the one central owner of every feature write and read."""

from functools import partial

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.cached_service import CachedService
from app.core.cache import use_cache
from app.core.exceptions import RecordInUseError, RecordNotFoundError
from app.core.pagination import Page, paginate
from app.features.characters.cache import invalidate_characters_cache
from app.features.characters.progression.feature_sync import reconcile_characters_for_source
from app.features.features.cache import FEATURE_CACHE_NAMESPACES, invalidate_feature_cache_after_commit
from app.features.features.crud.repository import FeatureRepository
from app.features.features.crud.schemas import (
    _FEAT_ONLY_FIELDS,
    _FEATURE_LEVEL_MAX,
    _FEATURE_LEVEL_MIN,
    _REQUIRED_FK_BY_SOURCE_TYPE,
    FeatureCreate,
    FeatureGetAllResponse,
    FeatureResponse,
    FeatureUpdate,
    NestedFeatureResponse,
)
from app.features.features.exceptions import InvalidFeatureSourceException
from app.models.features.feature_model import Feature

_STANDALONE_SOURCE_TYPES = (FeatureSourceType.FEAT, FeatureSourceType.OTHER)


def _get_fk_name(source_type: FeatureSourceType) -> str:
    """The source-FK column for ``source_type`` (raises for FEAT/OTHER)."""

    fk_name = _REQUIRED_FK_BY_SOURCE_TYPE[source_type]
    if fk_name is None:
        raise ValueError(
            f"source_type='{source_type.value}' has no source FK; per-source feature management is not supported."
        )

    return fk_name


class FeatureCrudService(CachedService[Feature, FeatureCreate, FeatureUpdate, FeatureResponse, FeatureGetAllResponse]):
    """
    The single feature service: every feature — standalone (FEAT/OTHER) or
    owned by a class/subclass/race/subrace/background — is created, read,
    updated and deleted through this one class.

    Every write is one transaction (``_unit_of_work``): the row change, the
    reconciliation of the owning record's characters and the post-commit
    cache purge (the shared ``features`` namespace plus the owning catalog's
    list and parent-read namespaces, see ``features.cache``). The parent
    catalogs cache their own feature lists; ``list_for_source`` is an
    uncached read for them.
    """

    repository: FeatureRepository

    cache_namespaces = FEATURE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize the service with the feature repository."""

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
        filters: dict | None = None,
        search: str | None = None,
    ) -> Page[FeatureGetAllResponse]:
        """
        Cached, paginated listing across every source type.

        Brief columns, including the denormalized ``has_static_effects``/
        ``has_choices`` flags, instead of eager-loading the full engine
        effect tree per row: ``FeatureGetAllResponse`` only needs the two
        booleans.
        """

        skip, limit = paginate(page, size)
        total = await self.repository.count(filters=filters, search=search)

        rows = await self.repository.get_brief(
            Feature.id,
            Feature.name,
            Feature.source_type,
            Feature.class_id,
            Feature.subclass_id,
            Feature.race_id,
            Feature.subrace_id,
            Feature.background_id,
            Feature.level,
            Feature.has_static_effects,
            Feature.has_choices,
            order_by=Feature.name,
            skip=skip,
            limit=limit,
            filters=filters,
            search=search,
        )

        items = [FeatureGetAllResponse.model_validate(row._mapping) for row in rows]
        return Page(items=items, total=total, page=page, size=size)

    async def list_for_source(self, source_type: FeatureSourceType, source_id: int) -> list[NestedFeatureResponse]:
        """
        Return every ``Feature`` row owned by ``source_id`` (ordered by id).

        Uncached on purpose: parent catalogs cache their own feature lists
        under dedicated namespaces. Raises ``ValueError`` when ``source_type``
        is FEAT or OTHER (no source FK).
        """

        rows = await self.repository.list_for_source(_get_fk_name(source_type), source_id)
        return [NestedFeatureResponse.model_validate(row) for row in rows]

    @staticmethod
    def _source_fk_value(source_type: FeatureSourceType, item: FeatureCreate | Feature) -> int | None:
        """The owning source's id for a feature (``None`` for FEAT/OTHER features)."""

        if source_type in _STANDALONE_SOURCE_TYPES:
            return None

        return getattr(item, _get_fk_name(source_type))

    async def _reconcile_characters(self, source_type: FeatureSourceType, source_id: int | None) -> None:
        """
        Reconcile auto-granted character features after a source-owned feature write.

        Runs in the open transaction (never commits); FEAT and OTHER features
        are never auto-granted, so they need no reconciliation.
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

        source_type = create_data.source_type

        async with self._atomic():
            item = await self.repository.create(create_data.model_dump(), commit=False)
            await self._reconcile_characters(source_type, self._source_fk_value(source_type, create_data))
            await invalidate_feature_cache_after_commit(self.repository.db, source_type)

        self.repository.mark_effects_empty(item)
        return self.response_schema.model_validate(item)

    @staticmethod
    def _validate_update(feature: Feature, fields: dict) -> None:
        """Reject ``level``/feat-column patches that would break the rules ``FeatureCreate`` enforces."""

        source_type = feature.source_type

        if "level" in fields:
            level = fields["level"]

            if level is None and source_type in (FeatureSourceType.CLASS, FeatureSourceType.SUBCLASS):
                raise InvalidFeatureSourceException(
                    "CLASS/SUBCLASS features require 'level' — it can only be changed, not cleared."
                )

            if level is not None and not (_FEATURE_LEVEL_MIN <= level <= _FEATURE_LEVEL_MAX):
                raise InvalidFeatureSourceException(
                    f"'level' must be between {_FEATURE_LEVEL_MIN} and {_FEATURE_LEVEL_MAX}."
                )

            if source_type == FeatureSourceType.FEAT and level is not None:
                raise InvalidFeatureSourceException("FEAT features do not use 'level' — set 'min_level' instead.")

        if source_type != FeatureSourceType.FEAT:
            feat_fields = [name for name in _FEAT_ONLY_FIELDS if fields.get(name) not in (None, "")]
            if feat_fields:
                raise InvalidFeatureSourceException(f"{', '.join(feat_fields)} only valid for FEAT-source features.")

        if "prerequisite_ability" in fields or "prerequisite_minimum_score" in fields:
            ability = fields.get("prerequisite_ability", feature.prerequisite_ability)
            minimum_score = fields.get("prerequisite_minimum_score", feature.prerequisite_minimum_score)
            if (ability is None) != (minimum_score is None):
                raise InvalidFeatureSourceException(
                    "prerequisite_ability and prerequisite_minimum_score must be set together."
                )

    async def update_feature(self, feature_id: int, update_data: FeatureUpdate) -> FeatureResponse:
        """
        Update a feature of any source type, keeping its id.

        ``source_type`` and its FK can't change — ownership is permanent.
        A CLASS/SUBCLASS feature's ``level`` is mandatory (1-20) and may be
        changed but never cleared. FEAT rows may edit ``min_level`` /
        ``prerequisite_*`` instead. Only a changed ``level`` re-reconciles the
        owning record's characters (grants and ability scores depend on
        nothing else); any other change just refreshes the caches of the
        characters holding the feature.
        """

        feature = await self._get_or_404(feature_id)
        fields = update_data.model_dump(exclude_unset=True)

        self._validate_update(feature, fields)

        changed = {field: value for field, value in fields.items() if getattr(feature, field) != value}
        if not changed:
            return self.response_schema.model_validate(feature)

        source_type = feature.source_type
        source_id = self._source_fk_value(source_type, feature)

        async with self._unit_of_work() as uow:
            for field, value in changed.items():
                setattr(feature, field, value)

            if "level" in changed and source_id is not None:
                await self._reconcile_characters(source_type, source_id)
            else:
                holders = await self.repository.holder_character_ids(feature_id)
                await uow.after_commit(partial(invalidate_characters_cache, holders))

            await invalidate_feature_cache_after_commit(self.repository.db, source_type)

        return self.response_schema.model_validate(feature)

    async def delete(self, feature_id: int) -> bool:
        """
        Delete a feature of any source type in one transaction, cascading away
        its ``CharacterFeature`` grants.

        A standalone FEAT/OTHER feature is only ever granted explicitly, so
        — like ``DELETE /feats/{id}`` — it can't be deleted while a
        character still holds it (409). Deleting a source-owned feature
        re-reconciles the owning record's characters before the commit.
        """

        feature = await self.repository.get_plain(feature_id)
        if feature is None:
            raise RecordNotFoundError(model_name="Feature", model_id=str(feature_id))

        source_type = feature.source_type
        source_id = self._source_fk_value(source_type, feature)

        if source_id is None and await self.repository.is_granted(feature_id):
            raise RecordInUseError(
                model_name="Feature", model_id=feature_id, reason="still granted to one or more characters"
            )

        async with self._atomic():
            await self.repository.delete(feature, commit=False)
            await self._reconcile_characters(source_type, source_id)
            await invalidate_feature_cache_after_commit(self.repository.db, source_type)

        return True
