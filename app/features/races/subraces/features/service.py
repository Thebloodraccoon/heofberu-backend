"""Subrace feature service: per-subrace SUBRACE-source feature CRUD."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.features.races.subraces.base import SubraceScopedMixin
from app.features.races.subraces.cache import invalidate_subrace_cache
from app.features.races.subraces.crud.repository import SubraceRepository
from app.features.races.subraces.crud.schemas import SubraceCreate, SubraceResponse, SubraceUpdate
from app.features.shared.features.nested_service import NestedFeatureService
from app.features.shared.features.schemas import FeatureUpdate, NestedFeatureCreate, NestedFeatureResponse
from app.models.subrace_model import Subrace


class SubraceFeatureService(
    SubraceScopedMixin,
    BaseService[Subrace, SubraceCreate, SubraceUpdate, SubraceResponse, None],
):
    """
    Everything about a subrace's own features.

    ``list_features``/``add_feature``/``update_feature``/``remove_feature``
    are race-scoped variants of the shared nested-feature operations: the
    source row is looked up via ``_get_or_404_for_race`` (so a subrace of
    a different race 404s) and the source type is always ``SUBRACE``.

    The write transaction also reconciles character grants (via
    ``reconcile_characters_for_source``), then purges the
    ``nested_features`` namespace — and, because race responses embed
    their subraces under the ``races`` namespace, that too — via
    :func:`invalidate_subrace_cache`.
    """

    repository: SubraceRepository

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=SubraceRepository(db),
            response_schema=SubraceResponse,
        )
        self._features = NestedFeatureService(db)

    async def list_features(self, race_id: int, subrace_id: int) -> list[NestedFeatureResponse]:
        """Return every SUBRACE-source feature of the subrace (cached under ``nested_features``)."""

        await self._get_or_404_for_race(race_id, subrace_id)
        return await self._features.list_for_source(FeatureSourceType.SUBRACE, subrace_id)

    async def add_feature(
        self,
        race_id: int,
        subrace_id: int,
        data: NestedFeatureCreate,
        created_by_id: int | None = None,
    ) -> NestedFeatureResponse:
        """
        Add one SUBRACE-source feature to a subrace.

        Creates a new feature owned by the subrace, then reconciles the
        grants of every character holding this subrace so qualifying
        characters gain it in the same transaction. Returns the created
        feature.
        """

        subrace = await self._get_or_404_for_race(race_id, subrace_id)
        return await self._mutate_feature(
            subrace,
            lambda: self._features.create_feature_for_source(
                FeatureSourceType.SUBRACE,
                subrace.id,
                data,
                created_by_id,
                commit=False,
            ),
        )

    async def update_feature(
        self,
        race_id: int,
        subrace_id: int,
        feature_id: int,
        update_data: FeatureUpdate,
    ) -> NestedFeatureResponse:
        """
        Update one SUBRACE-source feature of a subrace in place, keeping its id.

        The row keeps its id, so character grants and any player notes on
        them survive. Characters are reconciled in the same transaction.
        Returns the updated feature.
        """

        subrace = await self._get_or_404_for_race(race_id, subrace_id)
        fields = update_data.model_dump(exclude_unset=True)
        return await self._mutate_feature(
            subrace,
            lambda: self._features.update_feature_for_source(
                FeatureSourceType.SUBRACE,
                subrace.id,
                feature_id,
                fields,
                commit=False,
            ),
        )

    async def remove_feature(self, race_id: int, subrace_id: int, feature_id: int) -> None:
        """
        Remove one SUBRACE-source feature from a subrace.

        The feature row is deleted, cascading its ``character_features``
        grants away; characters are reconciled in the same transaction.
        """

        subrace = await self._get_or_404_for_race(race_id, subrace_id)
        await self._mutate_feature(
            subrace,
            lambda: self._features.delete_feature_for_source(
                FeatureSourceType.SUBRACE,
                subrace.id,
                feature_id,
                commit=False,
            ),
        )

    async def _mutate_feature(self, subrace: Subrace, mutate) -> NestedFeatureResponse | None:
        """
        Run ``mutate`` + character reconciliation in one transaction.

        Mirrors ``SourceFeatureMixin._mutate_feature`` (see
        ``app.features.shared.features.mixins``): duplicated rather than
        inherited because this service's feature source is always
        ``SUBRACE`` and its source row is looked up via
        ``_get_or_404_for_race`` instead of the mixin's plain
        ``_get_or_404``.
        """

        from app.features.characters.progression.feature_sync import reconcile_characters_for_source

        async with self._atomic():
            feature = await mutate()
            await reconcile_characters_for_source(self.repository.db, FeatureSourceType.SUBRACE, subrace.id)
            response = NestedFeatureResponse.model_validate(feature) if feature is not None else None

        await self._features.invalidate()
        await invalidate_subrace_cache()
        return response
