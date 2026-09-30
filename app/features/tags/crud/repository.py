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
    def _usage_counts(include_hidden: bool):
        """
        Subquery: one row per tag that's used at least once, with its total usage across all four
        catalogs — a single grouped aggregate instead of up to 4 correlated ``COUNT(*)`` subqueries
        (in SELECT, WHERE and a separate total ``COUNT(*)``) per tag.

        For non-GM readers (``include_hidden=False``) only published, public articles count — a
        draft's or GM-only article's tags must not show up (or be counted) for players.
        Races/subraces/backgrounds are always public.
        """

        article_links = select(article_tags.c.tag_id)
        if not include_hidden:
            article_links = article_links.join(Article, Article.id == article_tags.c.article_id).where(
                Article.status == ArticleStatus.PUBLISHED, Article.visibility == ArticleVisibility.PUBLIC
            )

        all_links = (
            select(race_tags.c.tag_id)
            .union_all(select(subrace_tags.c.tag_id), select(background_tags.c.tag_id), article_links)
            .subquery()
        )

        return select(all_links.c.tag_id, func.count().label("usage_count")).group_by(all_links.c.tag_id).subquery()

    @classmethod
    def _usage_source(cls, include_hidden: bool):
        """
        ``(joined Tag+usage source, usage_count column)`` for a listing query.

        Non-GM: INNER join, so a tag with zero visible usage is dropped entirely (``usage_count``
        then always non-null). GM: LEFT join so every tag appears, ``usage_count`` coalesced to 0.
        """

        usage = cls._usage_counts(include_hidden)
        if include_hidden:
            source = Tag.__table__.outerjoin(usage, usage.c.tag_id == Tag.id)
            usage_count = func.coalesce(usage.c.usage_count, 0).label("usage_count")
        else:
            source = Tag.__table__.join(usage, usage.c.tag_id == Tag.id)
            usage_count = usage.c.usage_count.label("usage_count")

        return source, usage_count

    async def is_visible(self, tag_id: int) -> bool:
        """Whether a non-GM reader may see the tag: it's carried by at least one record visible to them."""

        query = select(
            or_(
                exists().where(race_tags.c.tag_id == tag_id),
                exists().where(subrace_tags.c.tag_id == tag_id),
                exists().where(background_tags.c.tag_id == tag_id),
                exists().where(
                    article_tags.c.tag_id == tag_id,
                    article_tags.c.article_id == Article.id,
                    Article.status == ArticleStatus.PUBLISHED,
                    Article.visibility == ArticleVisibility.PUBLIC,
                ),
            )
        )
        return bool(await self.db.scalar(query))

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

        source, usage_count = self._usage_source(include_hidden)

        conditions = []
        if search:
            conditions.append(Tag.name.ilike(f"%{self._escape_like(search)}%", escape="\\"))

        order_by = [usage_count.desc(), func.lower(Tag.name)] if sort == "popular" else [func.lower(Tag.name), Tag.id]

        base = select(Tag.id, Tag.name, usage_count).select_from(source).where(*conditions)
        total = await self.db.scalar(select(func.count()).select_from(base.subquery()))
        result = await self.db.execute(base.order_by(*order_by).offset((page - 1) * size).limit(size))
        return list(result.all()), total or 0

    async def suggest(self, query: str, limit: int, *, include_hidden: bool) -> list[Any]:
        """
        Autocomplete: tags whose name contains ``query`` — prefix matches first, then most used, then A-Z.

        Same visibility rule as ``list_with_usage``.
        """

        escaped = self._escape_like(query)
        source, usage_count = self._usage_source(include_hidden)

        prefix_match = Tag.name.ilike(f"{escaped}%", escape="\\")
        conditions = [Tag.name.ilike(f"%{escaped}%", escape="\\")]

        result = await self.db.execute(
            select(Tag.id, Tag.name, usage_count)
            .select_from(source)
            .where(*conditions)
            .order_by(prefix_match.desc(), usage_count.desc(), func.lower(Tag.name))
            .limit(limit)
        )
        return list(result.all())
