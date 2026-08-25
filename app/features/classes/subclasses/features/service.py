"""Subclass feature service: per-subclass SUBCLASS-source feature CRUD."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FeatureSourceType
from app.core.base.service import BaseService
from app.features.classes.subclasses.base import SubclassScopedMixin
from app.features.classes.subclasses.cache import invalidate_subclass_cache
from app.features.classes.subclasses.crud.repository import SubclassRepository
from app.features.classes.subclasses.crud.schemas import SubclassCreate, SubclassResponse, SubclassUpdate
from app.features.shared.features.nested_service import NestedFeatureService
from app.features.shared.features.schemas import FeatureUpdate, NestedFeatureCreate, NestedFeatureResponse
from app.models.subclass_model import Subclass


class SubclassFeatureService(
    SubclassScopedMixin,
    BaseService[Subclass, SubclassCreate, SubclassUpdate, SubclassResponse, None],
):
    """

    Everything about a subclass's own features.

    ``list_features``/``add_feature``/``update_feature``/``remove_feature``
    are class-scoped variants of the shared nested-feature operations: the
    source row is looked up via ``_get_or_404_for_class`` (so a subclass of
    a different class 404s) and the source type is always ``SUBCLASS``.

    The write transaction also reconciles character grants (via
    ``reconcile_characters_for_source``), then purges the
    ``nested_features`` namespace — and, because ``ClassFullResponse``
    embeds subclass features under the ``classes`` namespace, that too —
    via :func:`invalidate_subclass_cache`.
    """

    repository: SubclassRepository

    def __init__(self, db: AsyncSession):
        super().__init__(
            repository=SubclassRepository(db),
            response_schema=SubclassResponse,
        )
        self._features = NestedFeatureService(db)

    async def list_features(self, class_id: int, subclass_id: int) -> list[NestedFeatureResponse]:
        """Return every SUBCLASS-source feature of the subclass (cached under ``nested_features``)."""

        await self._get_or_404_for_class(class_id, subclass_id)
        return await self._features.list_for_source(FeatureSourceType.SUBCLASS, subclass_id)

    async def add_feature(
        self,
        class_id: int,
        subclass_id: int,
        data: NestedFeatureCreate,
    ) -> NestedFeatureResponse:
        """

        Add one SUBCLASS-source feature to a subclass.

        Creates a new feature owned by the subclass, then reconciles the
        grants of every character holding this subclass so qualifying
        characters gain it in the same transaction. Returns the created
        feature.
        """

        subclass = await self._get_or_404_for_class(class_id, subclass_id)
        return await self._mutate_feature(
            subclass,
            lambda: self._features.create_feature_for_source(
                FeatureSourceType.SUBCLASS,
                subclass.id,
                data,
                commit=False,
            ),
        )

    async def update_feature(
        self,
        class_id: int,
        subclass_id: int,
        feature_id: int,
        update_data: FeatureUpdate,
    ) -> NestedFeatureResponse:
        """

        Update one SUBCLASS-source feature of a subclass in place, keeping its id.

        The row keeps its id, so character grants and any player notes on
        them survive. Characters are reconciled in the same transaction —
        raising a feature's ``level`` revokes it from characters below the
        new level. Returns the updated feature.
        """

        subclass = await self._get_or_404_for_class(class_id, subclass_id)
        fields = update_data.model_dump(exclude_unset=True)
        return await self._mutate_feature(
            subclass,
            lambda: self._features.update_feature_for_source(
                FeatureSourceType.SUBCLASS,
                subclass.id,
                feature_id,
                fields,
                commit=False,
            ),
        )

    async def remove_feature(self, class_id: int, subclass_id: int, feature_id: int) -> None:
        """

        Remove one SUBCLASS-source feature from a subclass.

        The feature row is deleted, cascading its ``character_features``
        grants away; characters are reconciled in the same transaction.
        """

        subclass = await self._get_or_404_for_class(class_id, subclass_id)
        await self._mutate_feature(
            subclass,
            lambda: self._features.delete_feature_for_source(
                FeatureSourceType.SUBCLASS,
                subclass.id,
                feature_id,
                commit=False,
            ),
        )

    async def _mutate_feature(self, subclass: Subclass, mutate) -> NestedFeatureResponse | None:
        """

        Run ``mutate`` + character reconciliation in one transaction.

        Mirrors ``SourceFeatureMixin._mutate_feature`` (see
        ``app.features.shared.features.mixins``): duplicated rather than
        inherited because this service's feature source is always
        ``SUBCLASS`` and its source row is looked up via
        ``_get_or_404_for_class`` instead of the mixin's plain
        ``_get_or_404``.
        """

        from app.features.characters.progression.feature_sync import reconcile_characters_for_source

        async with self._atomic():
            feature = await mutate()
            await reconcile_characters_for_source(self.repository.db, FeatureSourceType.SUBCLASS, subclass.id)
            response = NestedFeatureResponse.model_validate(feature) if feature is not None else None

        await self._features.invalidate()
        await invalidate_subclass_cache()
        return response
