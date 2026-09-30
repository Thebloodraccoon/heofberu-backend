"""Tag repository: base CRUD plus the in-use guard across every catalog that links tags."""

from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ArticleStatus, ArticleVisibility
from app.core.base.repository import BaseRepository
from app.core.exceptions import RecordAlreadyExistsError
from app.features.shared.tags.mixins import TagLookupMixin
from app.models.articles.article_association_models import article_tags
from app.models.articles.article_model import Article
from app.models.backgrounds.background_association_models import background_tags
from app.models.races.race_association_models import race_tags
from app.models.races.subrace_association_models import subrace_tags
from app.models.tag_model import Tag


class TagRepository(TagLookupMixin, BaseRepository[Tag]):
    """Tag-specific repository built on :class:`BaseRepository`."""

    def __init__(self, db: AsyncSession):
        """Initialize the tag repository with name uniqueness."""

        super().__init__(
            Tag,
            db,
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    async def is_in_use(self, tag_id: int) -> bool:
        """Check whether the tag is currently attached to any race/subrace/background/article."""

        query = select(
            or_(
                exists().where(race_tags.c.tag_id == tag_id),
                exists().where(subrace_tags.c.tag_id == tag_id),
                exists().where(background_tags.c.tag_id == tag_id),
                exists().where(article_tags.c.tag_id == tag_id),
            )
        )
        result = await self.db.execute(query)
        return bool(result.scalar())

    async def _check_uniqueness(self, data: dict[str, Any], exclude_id: int | None = None) -> None:
        """Raise ``RecordAlreadyExistsError`` if another tag has the same name, ignoring case."""

        name = data.get("name")
        if name is None:
            return

        stmt = select(Tag.id).where(func.lower(Tag.name) == name.lower())
        if exclude_id is not None:
            stmt = stmt.where(Tag.id != exclude_id)

        if await self.db.scalar(stmt) is not None:
            raise RecordAlreadyExistsError(model_name=self.model.__name__, field="name", value=name)

    @staticmethod
    def _usage_count(include_hidden: bool = True):
        """
        Scalar expression: how many records across all four catalogs carry the tag (correlated to ``Tag``).

        For non-GM readers (``include_hidden=False``) only published, public articles count — a draft's or
        GM-only article's tags must not show up (or be counted) for players. Races/subraces/backgrounds
        are always public.
        """

        def count_in(link_table, *conditions):
            return (
                select(func.count())
                .select_from(link_table)
                .where(link_table.c.tag_id == Tag.id, *conditions)
                .scalar_subquery()
            )

        articles = count_in(article_tags)
        if not include_hidden:
            articles = count_in(
                article_tags,
                article_tags.c.article_id == Article.id,
                Article.status == ArticleStatus.PUBLISHED,
                Article.visibility == ArticleVisibility.PUBLIC,
            )

        return count_in(race_tags) + count_in(subrace_tags) + count_in(background_tags) + articles

    async def is_visible(self, tag_id: int) -> bool:
        """Whether a non-GM reader may see the tag: it's carried by at least one record visible to them."""

        return bool(await self.db.scalar(select(self._usage_count(include_hidden=False) > 0).where(Tag.id == tag_id)))

    @staticmethod
    def _escape_like(term: str) -> str:
        """Escape LIKE wildcards so ``term`` is matched literally (paired with ``escape="\\"``)."""

        return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    async def list_with_usage(
        self, *, page: int, size: int, search: str | None, sort: str, include_hidden: bool
    ) -> tuple[list[Any], int]:
        """
        Paginated tags with their ``usage_count``; ``sort`` is ``name`` (A-Z) or ``popular`` (most used first).

        Non-GM readers get counts over visible records only, and tags with none are left out.
        """

        usage_expr = self._usage_count(include_hidden)
        conditions = [] if include_hidden else [usage_expr > 0]
        if search:
            conditions.append(Tag.name.ilike(f"%{self._escape_like(search)}%", escape="\\"))

        usage = usage_expr.label("usage_count")
        order_by = [usage.desc(), func.lower(Tag.name)] if sort == "popular" else [func.lower(Tag.name), Tag.id]

        total = await self.db.scalar(select(func.count()).select_from(Tag).where(*conditions))
        result = await self.db.execute(
            select(Tag.id, Tag.name, usage)
            .where(*conditions)
            .order_by(*order_by)
            .offset((page - 1) * size)
            .limit(size)
        )
        return list(result.all()), total or 0

    async def suggest(self, query: str, limit: int, *, include_hidden: bool) -> list[Any]:
        """
        Autocomplete: tags whose name contains ``query`` — prefix matches first, then most used, then A-Z.

        Same visibility rule as ``list_with_usage``.
        """

        escaped = self._escape_like(query)
        usage_expr = self._usage_count(include_hidden)
        usage = usage_expr.label("usage_count")
        prefix_match = Tag.name.ilike(f"{escaped}%", escape="\\")
        conditions = [Tag.name.ilike(f"%{escaped}%", escape="\\")]
        if not include_hidden:
            conditions.append(usage_expr > 0)

        result = await self.db.execute(
            select(Tag.id, Tag.name, usage)
            .where(*conditions)
            .order_by(prefix_match.desc(), usage.desc(), func.lower(Tag.name))
            .limit(limit)
        )
        return list(result.all())
