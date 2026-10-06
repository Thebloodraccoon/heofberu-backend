"""Article listing and full-text search queries (column rows, never ORM objects)."""

from typing import Any

from sqlalchemy import exists, func, literal_column, null, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnClause

from app.constants import ArticleProposalStatus
from app.core.pagination import Cursor, keyset_condition
from app.features.articles.base import ArticleScopedRepository
from app.features.articles.listing.filters import ArticleFilters
from app.features.articles.secrets import gm_stripped_sql
from app.features.articles.visibility import visibility_conditions
from app.models.articles.article_association_models import article_tags
from app.models.articles.article_model import Article
from app.models.articles.article_proposal_model import ArticleProposal
from app.models.articles.article_subtype_model import ArticleSubtype
from app.models.user_model import User

#: Minimum ``pg_trgm`` word-similarity for a title to count as a typo/prefix-tolerant match.
#: ``word_similarity`` (vs. plain ``similarity``) looks for the best-matching *substring* of the
#: title rather than comparing whole strings, so a short prefix like "Аур" still matches inside a
#: longer title like "Аурис, бог Солнца".
TITLE_SIMILARITY_THRESHOLD = 0.4

# Inline ``regconfig`` literals: a bound parameter would be sent as varchar, which Postgres
# won't accept where the text-search functions expect a ``regconfig``.
RUSSIAN_CONFIG: ColumnClause[Any] = literal_column("'russian'::regconfig")
SIMPLE_CONFIG: ColumnClause[Any] = literal_column("'simple'::regconfig")

SNIPPET_OPTIONS = "StartSel=<mark>, StopSel=</mark>, MaxFragments=2, MaxWords=25, MinWords=10, ShortWord=2"


class ArticleListingRepository(ArticleScopedRepository):
    """
    ``GET /articles`` and ``GET /articles/search`` queries.

    Both return plain column rows (``subtype_id``/``subtype_name``/``author_id``/``author_username`` flat;
    ``ArticleListingService`` nests them) and share ``_filter_conditions``, so a filter behaves the same in both.
    """

    def __init__(self, db: AsyncSession):
        """Bind to ``Article`` without eager loads (listing rows select their columns explicitly)."""

        super().__init__(db)

    async def list_articles(
        self, filters: ArticleFilters, *, skip: int, limit: int, sort: str = "title", after: Cursor | None = None
    ) -> tuple[list[Any], int | None]:
        """
        One page of filtered, sorted listing rows; each row also carries its ``sort_value`` (for cursors).

        Offset mode (``after is None``) returns the total match count from ``count() OVER()``; keyset mode returns
        only the rows strictly after ``after`` (``skip`` unused) and ``None`` as the total.
        """

        conditions = await self._filter_conditions(filters)
        key, descending = self._sort_key(sort)
        if after is not None:
            conditions.append(keyset_condition(key, Article.id, after, descending=descending))

        columns = [*self._row_columns(filters.include_hidden), key.label("sort_value")]
        if after is None:
            columns.append(func.count().over().label("total"))

        result = await self.db.execute(
            self._with_joins(select(*columns))
            .where(*conditions)
            .order_by(*((key.desc(), Article.id.desc()) if descending else (key, Article.id)))
            .offset(skip)
            .limit(limit)
        )
        rows = list(result.all())
        if after is not None:
            return rows, None

        return rows, await self._total(rows, conditions, skip)

    async def search_articles(
        self, query: str, filters: ArticleFilters, *, skip: int, limit: int
    ) -> tuple[list[Any], int]:
        """
        Full-text + typo-tolerant title search, best match first.

        A row matches when its weighted search vector (Russian OR simple config, so both stemmed and literal terms
        hit) matches ``query``, or its title is trigram-word-similar to it ("Аур" finds "Аурис, бог Солнца").
        ``rank`` blends ``ts_rank`` with title similarity; ``snippet`` is a ``<mark>``-wrapped ``ts_headline``
        fragment of title/excerpt/body (the rest of it is raw markdown).

        Ranking and paging run first over ids only; the expensive ``ts_headline`` runs just for the returned page.

        Non-GM readers search ``search_vector`` (built without ``:::gm`` blocks) and get the excerpt and snippet
        with GM blocks stripped, so a secret can neither match nor show up; GMs search ``search_vector_gm``.
        """

        russian_query = func.websearch_to_tsquery(RUSSIAN_CONFIG, query)
        combined_query = russian_query.op("||")(func.websearch_to_tsquery(SIMPLE_CONFIG, query))
        title_match = Article.title.op("%>")(query)

        if filters.include_hidden:
            vector, body = Article.search_vector_gm, Article.body_markdown
        else:
            vector, body = Article.search_vector, gm_stripped_sql(Article.body_markdown)

        conditions = [or_(vector.op("@@")(combined_query), title_match), *await self._filter_conditions(filters)]

        rank = (func.ts_rank(vector, combined_query) + func.word_similarity(query, Article.title)).label("rank")
        ranked_page = (
            select(Article.id.label("id"), rank, func.count().over().label("total"))
            .where(*conditions)
            .order_by(rank.desc(), Article.id)
            .offset(skip)
            .limit(limit)
            .subquery("ranked_page")
        )

        excerpt = func.coalesce(self._excerpt_column(filters.include_hidden), "")
        snippet = func.ts_headline(
            RUSSIAN_CONFIG, func.concat_ws(" ", Article.title, excerpt, body), combined_query, SNIPPET_OPTIONS
        ).label("snippet")

        # SET LOCAL rejects bind params; TITLE_SIMILARITY_THRESHOLD is a hardcoded constant, so inlining it is safe.
        await self.db.execute(text(f"SET LOCAL pg_trgm.word_similarity_threshold = {TITLE_SIMILARITY_THRESHOLD}"))
        columns = [*self._row_columns(filters.include_hidden), ranked_page.c.rank, snippet, ranked_page.c.total]
        result = await self.db.execute(
            self._with_joins(select(*columns).join(ranked_page, ranked_page.c.id == Article.id)).order_by(
                ranked_page.c.rank.desc(), Article.id
            )
        )
        rows = list(result.all())
        return rows, await self._total(rows, conditions, skip)

    async def _filter_conditions(self, filters: ArticleFilters) -> list:
        """Visibility plus every requested filter, ANDed (see ``ArticleFilters``)."""

        conditions = visibility_conditions(filters.include_hidden)
        if filters.author_id is not None:
            conditions.append(Article.author_id == filters.author_id)
        if filters.statuses:
            conditions.append(Article.status.in_(filters.statuses))
        if filters.has_pending_proposals is not None:
            pending = exists().where(
                ArticleProposal.article_id == Article.id, ArticleProposal.status == ArticleProposalStatus.PENDING
            )
            conditions.append(pending if filters.has_pending_proposals else ~pending)
        if filters.article_types or filters.subtype_ids:
            conditions.append(await self._type_condition(filters.article_types, filters.subtype_ids))
        if filters.tag_ids:
            conditions.append(self._tag_condition(filters.tag_ids, filters.match_all_tags))

        return conditions

    async def _type_condition(self, article_types: tuple[str, ...], subtype_ids: tuple[int, ...]):
        """
        Type/subtype filter where a subtype refines only its own type (faceted search).

        A type with some of its subtypes picked contributes only those subtypes; a type with none picked
        contributes all of its articles: ``subtype_id IN (picked) OR type IN (types without a picked subtype)``.
        Subtypes picked without their type still match (their type is implied).
        """

        if not subtype_ids:
            return Article.article_type.in_(article_types)

        refined = set(
            (
                await self.db.execute(
                    select(ArticleSubtype.article_type).where(ArticleSubtype.id.in_(subtype_ids)).distinct()
                )
            ).scalars()
        )
        whole_types = [t for t in article_types if t not in refined]

        return or_(Article.subtype_id.in_(subtype_ids), Article.article_type.in_(whole_types))

    @staticmethod
    def _tag_condition(tag_ids: tuple[int, ...], match_all: bool):
        """Articles carrying any (default) or all of ``tag_ids``."""

        subquery = select(article_tags.c.article_id).where(article_tags.c.tag_id.in_(tag_ids))
        if match_all:
            subquery = subquery.group_by(article_tags.c.article_id).having(
                func.count(func.distinct(article_tags.c.tag_id)) == len(set(tag_ids))
            )

        return Article.id.in_(subquery)

    def _row_columns(self, include_hidden: bool) -> list:
        """Columns of a listing/search row (``ArticleGetAllResponse`` before nesting)."""

        return [
            Article.id,
            Article.slug,
            Article.title,
            self._excerpt_column(include_hidden),
            Article.article_type,
            ArticleSubtype.id.label("subtype_id"),
            ArticleSubtype.name.label("subtype_name"),
            Article.status,
            Article.visibility,
            Article.author_id,
            User.username.label("author_username"),
            self._pending_proposals_column(include_hidden),
        ]

    @staticmethod
    def _with_joins(stmt):
        """Outer-join the subtype and author ``_row_columns`` reads."""

        return stmt.outerjoin(ArticleSubtype, ArticleSubtype.id == Article.subtype_id).outerjoin(
            User, User.id == Article.author_id
        )

    @staticmethod
    def _excerpt_column(include_hidden: bool):
        """``excerpt`` as the reader may see it: GM-only blocks stripped in SQL for non-GMs."""

        if include_hidden:
            return Article.excerpt

        return gm_stripped_sql(Article.excerpt).label("excerpt")

    @staticmethod
    def _pending_proposals_column(include_hidden: bool):
        """The article's pending proposal count for GMs (correlated subquery), ``NULL`` for other readers."""

        if not include_hidden:
            return null().label("pending_proposals")

        return (
            select(func.count())
            .where(ArticleProposal.article_id == Article.id, ArticleProposal.status == ArticleProposalStatus.PENDING)
            .scalar_subquery()
            .label("pending_proposals")
        )

    @staticmethod
    def _sort_key(sort: str) -> tuple[Any, bool]:
        """``(sort expression, descending)`` of a listing ``sort``; ``Article.id`` (same direction) breaks ties."""

        published = func.coalesce(Article.published_at, Article.created_at)
        return {
            "title": (Article.title, False),
            "newest": (published, True),
            "oldest": (published, False),
            "updated": (Article.updated_at, True),
        }[sort]

    async def _total(self, rows: list, conditions: list, skip: int) -> int:
        """
        Total match count: from the page's ``count() OVER()`` column, else (no row on this page) 0 on the first
        page or a separate COUNT for a page past the end.
        """

        if rows:
            return rows[0].total or 0
        if not skip:
            return 0

        return await self.db.scalar(select(func.count()).select_from(Article).where(*conditions)) or 0
