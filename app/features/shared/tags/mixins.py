"""Shared tag mixins for lookup and full-replace operations against the shared Tag dictionary."""

from typing import Any

from app.core.base.repository import RepositoryMixin
from app.core.base.service import ServiceMixin
from app.models.tag_model import Tag


class TagLookupMixin(RepositoryMixin):
    """Resolve tag IDs to Tag rows via the generic id-IN lookup."""

    async def get_tags_by_ids(self, tag_ids: list[int]) -> list[Tag]:
        """Fetch the tags matching ``tag_ids`` (order not guaranteed)."""

        return await self.get_many_by_ids(Tag, tag_ids)


class TagsReplaceMixin(RepositoryMixin):
    """
    Fully replace a source record's tags in its many-to-many association table.

    Shared body for every per-catalog tags repository (``RaceTagsRepository``,
    ``SubraceTagsRepository``, ``BackgroundTagsRepository``,
    ``ArticleTagsRepository``, ...); a subclass only declares the three
    class attributes below — the wiring to its own base repository (for
    ``replace_association``) still requires one thin subclass per catalog,
    same as ``RaceImageService``/``EntityImageService``.
    """

    #: The association ``Table`` linking the entity to ``tags`` (e.g. ``race_tags``).
    _tags_association_table: Any
    #: The association table's FK column name pointing back at the owning entity (e.g. ``"race_id"``).
    _tags_entity_column: str
    #: The entity's ORM model class, used only to build the identity-only row ``replace_association`` needs.
    _tags_entity_model: Any

    async def set_tags(self, entity_id: int, tags: list[Tag]) -> None:
        """Replace all tags for ``entity_id`` with the given list."""

        await self.replace_association(
            self._tags_association_table,
            self._tags_entity_model(id=entity_id),
            self._tags_entity_column,
            "tag_id",
            [tag.id for tag in (tags or [])],
        )


class TagsManagerMixin(ServiceMixin):
    """Fully replace the tags attached to a source record."""

    async def set_tags(self, source_id: int, data: Any) -> Any:
        """Fully replace the tags attached to ``source_id`` (check, resolve, write and purge in one transaction)."""

        async with self._atomic():
            await self._exists_or_404(source_id)
            tags = await self._resolve_tags(data.tag_ids)

            await self.repository.set_tags(source_id, tags)
            await self._after_tags_set(source_id)

        return await self._get_response(source_id)

    async def _after_tags_set(self, source_id: int) -> None:
        """Post-write cache hook (runs inside the transaction); purges the service namespaces by default."""

        await self._invalidate_cache()

    async def _resolve_tags(self, tag_ids: list[int] | None) -> list[Tag] | None:
        """Resolve ``tag_ids`` to ``Tag`` rows, or ``None`` when absent/empty."""

        if not tag_ids:
            return None

        return await self.resolve_ids(self.repository.get_tags_by_ids, tag_ids, "Tags")
