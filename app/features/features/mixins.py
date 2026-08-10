"""
Reusable per-source feature CRUD mixin for the reference catalog services.

The race/class/background/feat services each exposed an identical trio
(``add_feature`` / ``update_feature`` / ``remove_feature``) that wrapped a
``FeatureService`` call plus the character-grant reconciliation in one
``_atomic()`` transaction. :class:`SourceFeatureMixin` defines that trio
once; a concrete service only declares ``_feature_source_type`` (and, for
subclasses, reuses ``_mutate_feature`` with a different source type).
"""

from collections.abc import Awaitable, Callable
from typing import Any

from app.constants import FeatureSourceType
from app.features.characters.progression.feature_sync import reconcile_characters_for_source
from app.features.features.schemas import FeatureUpdate, NestedFeatureCreate


class SourceFeatureMixin:
    """Add/update/remove one feature owned by a source record, atomically."""

    _feature_source_type: FeatureSourceType

    async def add_feature(
        self, source_id: int, data: NestedFeatureCreate, created_by_id: int | None = None
    ) -> Any:
        """
        Add one feature to the source (``source_type: <_feature_source_type>``).

        Creates a new feature row owned by the source, then reconciles the
        grants of every affected character in the same transaction.
        """

        source = await self._get_or_404(source_id)
        await self._mutate_feature(
            source,
            self._feature_source_type,
            lambda: self._features.create_feature_for_source(
                self._feature_source_type, source.id, data, created_by_id, commit=False
            ),
        )

        return await self._get_response(source_id)

    async def update_feature(
        self, source_id: int, feature_id: int, update_data: FeatureUpdate
    ) -> Any:
        """
        Update one source-owned feature in place, keeping its id.

        The row keeps its id, so character grants and any player notes on
        them survive. Characters are reconciled in the same transaction —
        e.g. raising a feature's ``level`` revokes it from characters below
        the new level.
        """

        source = await self._get_or_404(source_id)
        fields = update_data.model_dump(exclude_unset=True)

        await self._mutate_feature(
            source,
            self._feature_source_type,
            lambda: self._features.update_feature_for_source(
                self._feature_source_type, source.id, feature_id, fields, commit=False
            ),
        )

        return await self._get_response(source_id)

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
    ) -> None:
        """Run ``mutate`` + character reconciliation in one transaction, then invalidate the cache.

        Note: the source is deliberately *not* expired after the commit. Reads
        always go through ``get_by_id``/``get_subclass`` which use
        ``populate_existing=True``, so the next fetch re-reads the fresh rows.
        ``db.expire(source)`` instead left the instance expired in a shared
        session, and serializing it (``model_validate``) triggered an async
        lazy-load outside a greenlet → MissingGreenlet.
        """

        async with self._atomic():
            await mutate()
            await reconcile_characters_for_source(self.repository.db, source_type, source.id)

        await self._invalidate_cache()
