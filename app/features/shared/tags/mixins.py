"""Shared tag mixins for lookup and full-replace operations against the shared Tag dictionary."""

from typing import Any

from app.models.tag_model import Tag


class TagLookupMixin:
    """Resolve tag IDs to Tag rows via the generic id-IN lookup."""

    async def get_tags_by_ids(self, tag_ids: list[int]) -> list[Tag]:
        """Fetch the tags matching ``tag_ids`` (order not guaranteed)."""

        return await self.get_many_by_ids(Tag, tag_ids)


class TagsReplaceMixin:
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

    async def set_tags(self, entity_id: int, tags: list[Tag], *, commit: bool = True) -> None:
        """Replace all tags for ``entity_id`` with the given list."""

        await self.replace_association(
            self._tags_association_table,
            self._tags_entity_model(id=entity_id),
            self._tags_entity_column,
            "tag_id",
            [tag.id for tag in (tags or [])],
            commit=commit,
        )


class TagsManagerMixin:
    """Fully replace the tags attached to a source record."""

    _set_tags_method: str = "set_tags"

    async def set_tags(self, source_id: int, data: Any) -> Any:
        """Fully replace the tags attached to ``source_id``."""

        await self._exists_or_404(source_id)
        tags = await self._resolve_tags(data.tag_ids)

        await getattr(self.repository, self._set_tags_method)(source_id, tags)
        await self._invalidate_cache()

        return await self._get_response(source_id)

    async def _resolve_tags(self, tag_ids: list[int] | None) -> list[Tag] | None:
        """Resolve ``tag_ids`` to ``Tag`` rows, or ``None`` when absent/empty."""

        if not tag_ids:
            return None

        return await self.resolve_ids(self.repository.get_tags_by_ids, tag_ids, "Tags")
