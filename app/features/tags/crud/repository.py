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
    def _carried_by_visible_record(tag_id):
        """
        Boolean clause: the tag is attached to at least one record a non-GM reader may see.

        Races/subraces/backgrounds are always public; articles count only when published and public.
        ``tag_id`` is either a literal id or the outer ``Tag.id`` column (the clause then correlates to it).
        """

        return or_(
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

    @staticmethod
    def _usage_counts(include_hidden: bool, tag_filter=None):
        """
        Subquery: one row per tag that's used at least once, with its total usage across all four
        catalogs — a single grouped aggregate instead of up to 4 correlated ``COUNT(*)`` subqueries.

        ``tag_filter`` (a list of ids or a ``select`` of ids) restricts every link table to those tags, so a
        listing page or a suggestion list aggregates only the rows it shows instead of all four tables.

        For non-GM readers (``include_hidden=False``) only published, public articles count — a
        draft's or GM-only article's tags must not show up (or be counted) for players.
        Races/subraces/backgrounds are always public.
        """

        link_columns = [race_tags.c.tag_id, subrace_tags.c.tag_id, background_tags.c.tag_id, article_tags.c.tag_id]
        branches = [select(column) for column in link_columns]
        if not include_hidden:
            branches[3] = (
                branches[3]
                .join(Article, Article.id == article_tags.c.article_id)
                .where(Article.status == ArticleStatus.PUBLISHED, Article.visibility == ArticleVisibility.PUBLIC)
            )
        if tag_filter is not None:
            branches = [
                branch.where(column.in_(tag_filter)) for branch, column in zip(branches, link_columns, strict=False)
            ]

        all_links = branches[0].union_all(*branches[1:]).subquery()

        return select(all_links.c.tag_id, func.count().label("usage_count")).group_by(all_links.c.tag_id).subquery()

    def _visible_conditions(self, include_hidden: bool) -> list:
        """Row filter on ``Tag``: non-GM readers only see tags carried by a record they can see."""

        return [] if include_hidden else [self._carried_by_visible_record(Tag.id)]

    async def is_visible(self, tag_id: int) -> bool:
        """Whether a non-GM reader may see the tag: it's carried by at least one record visible to them."""

        return bool(await self.db.scalar(select(self._carried_by_visible_record(tag_id))))

    @staticmethod
    def _escape_like(term: str) -> str:
        """Escape LIKE wildcards so ``term`` is matched literally (paired with a backslash ``escape``)."""

        return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    async def list_with_usage(
        self, *, page: int, size: int, search: str | None, sort: str, include_hidden: bool
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Paginated tags with their ``usage_count``; ``sort`` is ``name`` (A-Z) or ``popular`` (most used first).

        Non-GM readers get counts over visible records only, and tags with none are left out. The total
        never needs the counts; by name only the returned page is aggregated, by popularity every
        matching tag is.
        """

        conditions = self._visible_conditions(include_hidden)
        if search:
            conditions.append(Tag.name.ilike(f"%{self._escape_like(search)}%", escape="\\"))

        total = await self.db.scalar(select(func.count()).select_from(Tag).where(*conditions)) or 0
        offset = (page - 1) * size

        if sort == "popular":
            usage = self._usage_counts(include_hidden, tag_filter=select(Tag.id).where(*conditions))
            usage_count = func.coalesce(usage.c.usage_count, 0)
            result = await self.db.execute(
                select(Tag.id, Tag.name, usage_count.label("usage_count"))
                .select_from(Tag.__table__.outerjoin(usage, usage.c.tag_id == Tag.id))
                .where(*conditions)
                .order_by(usage_count.desc(), func.lower(Tag.name), Tag.id)
                .offset(offset)
                .limit(size)
            )
            return [dict(row._mapping) for row in result], total

        result = await self.db.execute(
            select(Tag.id, Tag.name)
            .where(*conditions)
            .order_by(func.lower(Tag.name), Tag.id)
            .offset(offset)
            .limit(size)
        )
        page_rows = list(result.all())
        counts = await self._counts_for([row.id for row in page_rows], include_hidden)

        return [{"id": row.id, "name": row.name, "usage_count": counts.get(row.id, 0)} for row in page_rows], total

    async def _counts_for(self, tag_ids: list[int], include_hidden: bool) -> dict[int, int]:
        """``{tag_id: usage_count}`` for just ``tag_ids`` (tags without usage are absent)."""

        if not tag_ids:
            return {}

        usage = self._usage_counts(include_hidden, tag_filter=tag_ids)
        result = await self.db.execute(select(usage.c.tag_id, usage.c.usage_count))
        return {row.tag_id: row.usage_count for row in result}

    async def suggest(self, query: str, limit: int, *, include_hidden: bool) -> list[dict[str, Any]]:
        """
        Autocomplete: tags whose name contains ``query`` — prefix matches first, then most used, then A-Z.

        Same visibility rule as ``list_with_usage``; usage is aggregated only for the matching tags.
        """

        escaped = self._escape_like(query)
        conditions = [*self._visible_conditions(include_hidden), Tag.name.ilike(f"%{escaped}%", escape="\\")]
        usage = self._usage_counts(include_hidden, tag_filter=select(Tag.id).where(*conditions))
        usage_count = func.coalesce(usage.c.usage_count, 0)

        result = await self.db.execute(
            select(Tag.id, Tag.name, usage_count.label("usage_count"))
            .select_from(Tag.__table__.outerjoin(usage, usage.c.tag_id == Tag.id))
            .where(*conditions)
            .order_by(Tag.name.ilike(f"{escaped}%", escape="\\").desc(), usage_count.desc(), func.lower(Tag.name))
            .limit(limit)
        )
        return [dict(row._mapping) for row in result]
