"""
Reusable per-source feature CRUD mixin for the reference catalog services.

The race/class/background services each exposed an identical trio
(``add_feature`` / ``update_feature`` / ``remove_feature``) plus a
``list_features`` read that wraps a :class:`NestedFeatureService` call and
the character-grant reconciliation in one ``_atomic()`` transaction.
:class:`SourceFeatureMixin` defines those once; a concrete service only
declares ``_feature_source_type`` (and, for subclasses/subraces, reuses
``_mutate_feature`` with a different source type).

Per-source feature writes return the affected :class:`NestedFeatureResponse`
directly (the parent record responses no longer embed their features — a
client reads them via ``GET /{source}/{id}/features``).
"""

from collections.abc import Awaitable, Callable
from typing import Any

from app.constants import FeatureSourceType
from app.features.characters.progression.feature_sync import reconcile_characters_for_source
from app.features.shared.features.schemas import FeatureUpdate, NestedFeatureCreate, NestedFeatureResponse


class SourceFeatureMixin:
    """Add/update/remove/list one source record's features, atomically."""

    _feature_source_type: FeatureSourceType

    async def list_features(self, source_id: int) -> list[NestedFeatureResponse]:
        """Return every feature owned by the source (cached under ``nested_features``)."""

        source = await self._get_or_404(source_id)
        return await self._features.list_for_source(self._feature_source_type, source.id)

    async def add_feature(self, source_id: int, data: NestedFeatureCreate) -> NestedFeatureResponse:
        """
        Add one feature to the source (``source_type: <_feature_source_type>``).

        Creates a new feature row owned by the source, then reconciles the
        grants of every affected character in the same transaction. Returns
        the created feature.
        """

        source = await self._get_or_404(source_id)
        return await self._mutate_feature(
            source,
            self._feature_source_type,
            lambda: self._features.create_feature_for_source(
                self._feature_source_type, source.id, data, commit=False
            ),
        )

    async def update_feature(
        self, source_id: int, feature_id: int, update_data: FeatureUpdate
    ) -> NestedFeatureResponse:
        """
        Update one source-owned feature in place, keeping its id.

        The row keeps its id, so character grants and any player notes on
        them survive. Characters are reconciled in the same transaction —
        e.g. raising a feature's ``level`` revokes it from characters below
        the new level. Returns the updated feature.
        """

        source = await self._get_or_404(source_id)
        fields = update_data.model_dump(exclude_unset=True)

        return await self._mutate_feature(
            source,
            self._feature_source_type,
            lambda: self._features.update_feature_for_source(
                self._feature_source_type, source.id, feature_id, fields, commit=False
            ),
        )

    async def remove_feature(self, source_id: int, feature_id: int) -> None:
        """
        Remove one feature from the source.

        The feature row is deleted, cascading its ``character_features``
        grants away; characters are reconciled in the same transaction.
        """

        source = await self._get_or_404(source_id)
        await self._mutate_feature(
            source,
            self._feature_source_type,
            lambda: self._features.delete_feature_for_source(
                self._feature_source_type, source.id, feature_id, commit=False
            ),
        )

    async def _mutate_feature(
        self,
        source: Any,
        source_type: FeatureSourceType,
        mutate: Callable[[], Awaitable[Any]],
    ) -> NestedFeatureResponse | None:
        """
        Run ``mutate`` + character reconciliation in one transaction.

        Returns the created/updated feature serialized as a
        ``NestedFeatureResponse`` (or ``None`` for a removal). The response
        is built *inside* the transaction while the row is still loaded —
        serializing the ORM instance after ``commit`` would hit expired
        attributes (async lazy-load → MissingGreenlet). The
        ``nested_features`` cache namespace is purged after the commit.
        """

        async with self._atomic():
            feature = await mutate()
            await reconcile_characters_for_source(self.repository.db, source_type, source.id)
            response = NestedFeatureResponse.model_validate(feature) if feature is not None else None

        await self._features.invalidate()
        return response
