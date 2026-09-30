"""Article repository: base CRUD, eager-loaded tags/images, ltree path maintenance, no in-use delete guard."""

from typing import Any

from sqlalchemy import and_, exists, func, literal_column, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, load_only, selectinload
from sqlalchemy_utils import Ltree

from app.constants import ARTICLE_GM_BLOCK_SQL_PATTERN, ArticleStatus, ArticleVisibility
from app.core.base.repository import BaseRepository
from app.features.articles.slug import slugify
from app.models.articles.article_association_models import article_tags
from app.models.articles.article_image_model import ArticleImage
from app.models.articles.article_model import Article
from app.models.articles.article_subtype_model import ArticleSubtype


#: Minimum ``pg_trgm`` word-similarity for a title to count as a typo/prefix-tolerant match.
#: ``word_similarity`` (vs. plain ``similarity``) looks for the best-matching *substring* of the
#: title rather than comparing whole strings, so a short prefix like "Аур" still matches inside a
#: longer title like "Аурис, бог Солнца".
TITLE_SIMILARITY_THRESHOLD = 0.4

# Inline ``regconfig`` literals: a bound parameter would be sent as varchar, which Postgres
# won't accept where the text-search functions expect a ``regconfig``.
RUSSIAN_CONFIG = literal_column("'russian'::regconfig")
SIMPLE_CONFIG = literal_column("'simple'::regconfig")


class ArticleRepository(BaseRepository[Article]):
    """
    Article repository with eager-loaded tags and gallery images.

    No ``check_in_use_on_delete``: deleting an article that's someone's
    ``parent_id`` just detaches its children (``ondelete="SET NULL"``, see
    ``app/models/articles/article_model.py``) instead of being blocked —
    unlike a race/class/skill, nothing downstream depends on an article
    existing.
    """

    def __init__(self, db: AsyncSession):
        """Initialize the repository with eager-loaded tags and images."""

        super().__init__(
            Article,
            db,
            default_load_options=[selectinload(Article.tags), selectinload(Article.images)],
            search_fields=["title", "slug"],
            unique_fields=["slug"],
        )

    async def apply_update(self, article: Article, fields: dict, *, commit: bool = True) -> Article:
        """
        Apply ``fields`` onto ``article`` (uniqueness-checked), committing or just flushing.

        ``BaseRepository.update`` always commits; this variant honors ``commit=False``
        so it can join an ``_atomic()`` block together with ``set_path``.
        """

        await self._check_uniqueness(fields, exclude_id=article.id)

        for field, value in fields.items():
            setattr(article, field, value)

        await self.commit_or_flush(commit=commit)

        return article

    async def generate_unique_slug(self, title: str, *, exclude_id: int | None = None) -> str:
        """
        Build a slug from ``title`` that no article uses yet: ``base``, then ``base-2``, ``base-3``, ...

        ``exclude_id`` ignores that article's own current slug (re-slugging on rename).
        A concurrent create can still race to the same value; the ``slug`` unique
        constraint is the backstop for that.
        """

        base = slugify(title)
        stmt = select(Article.slug).where(or_(Article.slug == base, Article.slug.like(f"{base}-%")))
        if exclude_id is not None:
            stmt = stmt.where(Article.id != exclude_id)
        result = await self.db.execute(stmt)
        taken = set(result.scalars().all())

        candidate, suffix = base, 2
        while candidate in taken:
            candidate = f"{base}-{suffix}"
            suffix += 1

        return candidate

    async def is_self_or_descendant(self, article_id: int, candidate_id: int) -> bool:
        """Return whether ``candidate_id`` is ``article_id`` itself or sits anywhere in its subtree."""

        if candidate_id == article_id:
            return True

        article_path = await self.db.scalar(select(Article.path).where(Article.id == article_id))
        if article_path is None:
            return False

        stmt = select(Article.id).where(Article.id == candidate_id, Article.path.op("<@")(article_path))
        return await self.db.scalar(stmt) is not None

    async def get_id_by_slug(self, slug: str) -> int | None:
        """Return the id of the article with this ``slug`` (any visibility), or ``None``."""

        result = await self.db.execute(select(Article.id).where(Article.slug == slug))
        return result.scalar_one_or_none()

    async def get_subtype_type(self, subtype_id: int) -> str | None:
        """Return the ``article_type`` a subtype belongs to, or ``None`` if it doesn't exist."""

        return await self.db.scalar(select(ArticleSubtype.article_type).where(ArticleSubtype.id == subtype_id))

    async def list_image_keys(self, article_id: int) -> list[tuple[int, str]]:
        """Return ``(id, storage_key)`` of every image owned by the article (for storage cleanup on delete)."""

        result = await self.db.execute(
            select(ArticleImage.id, ArticleImage.storage_key).where(ArticleImage.article_id == article_id)
        )
        return [(row.id, row.storage_key) for row in result]

    async def list_child_ids(self, article_id: int) -> list[int]:
        """Return the ids of every direct child (any visibility) — used to fix up ``path`` after a delete."""

        result = await self.db.execute(select(Article.id).where(Article.parent_id == article_id))
        return list(result.scalars().all())

    async def set_path(self, article_id: int, parent_id: int | None, *, commit: bool = True) -> None:
        """
        Compute and persist ``path`` for ``article_id`` from its parent's ``path``.

        If the article already had a ``path`` (i.e. this is a re-parent, not
        the initial set on create), every existing descendant is re-rooted
        under the new path in the same statement (an ltree "move subtree")
        so ancestor/descendant queries stay correct for the whole subtree.

        Callers must have rejected cycles first (see ``is_self_or_descendant``;
        ``ArticleCrudService`` does).
        """

        if parent_id is None:
            new_path = str(article_id)
        else:
            parent_path = await self.db.scalar(select(Article.path).where(Article.id == parent_id))
            new_path = f"{parent_path}.{article_id}" if parent_path else str(article_id)

        old_path = await self.db.scalar(select(Article.path).where(Article.id == article_id))

        await self.db.execute(update(Article).where(Article.id == article_id).values(path=Ltree(new_path)))

        if old_path:
            await self.db.execute(
                text(
                    "UPDATE articles "
                    "SET path = CAST(:new_path AS ltree) || subpath(path, nlevel(CAST(:old_path AS ltree))) "
                    "WHERE path <@ CAST(:old_path AS ltree) AND id != :article_id"
                ),
                {"new_path": new_path, "old_path": str(old_path), "article_id": article_id},
            )

        await self.commit_or_flush(commit=commit)

    async def _count(self, model, conditions: list) -> int:
        """Fallback total for an empty page (``count() OVER()`` yields no row when nothing matches)."""

        return await self.db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0

    @staticmethod
    def _brief_load_options() -> list:
        """Columns an ``ArticleBrief`` response actually uses (tree endpoints don't need body/tags/images)."""

        return [load_only(Article.id, Article.slug, Article.title, Article.article_type, Article.subtype_id)]

    @staticmethod
    def _visibility_conditions(include_hidden: bool) -> list:
        """Row filters hiding unpublished and GM-only articles from non-GM readers."""

        if include_hidden:
            return []

        return [Article.status == ArticleStatus.PUBLISHED, Article.visibility == ArticleVisibility.PUBLIC]

    @staticmethod
    def _excerpt_column(include_hidden: bool):
        """``excerpt`` as the reader may see it: GM-only blocks stripped for non-GMs."""

        if include_hidden:
            return Article.excerpt

        return func.regexp_replace(Article.excerpt, ARTICLE_GM_BLOCK_SQL_PATTERN, " ", "g").label("excerpt")

    async def _type_condition(self, article_types: list[str], subtype_ids: list[int]):
        """
        Type/subtype filter where a subtype refines only its own type (faceted search).

        A type with some of its subtypes picked contributes only those subtypes; a type with none
        picked contributes all of its articles: ``type IN (types w/o picked subtypes) OR subtype_id IN
        (picked)``. Subtypes picked without their type still match (their type is implied).
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
    def _subtype_columns() -> list:
        """Listing columns for the (optional) subtype; ``ArticleCrudService`` nests them into ``subtype``."""

        return [ArticleSubtype.id.label("subtype_id"), ArticleSubtype.name.label("subtype_name")]

    @staticmethod
    def _tag_condition(tag_ids: list[int], match_all: bool):
        """Articles carrying any (default) or all of ``tag_ids``."""

        subquery = select(article_tags.c.article_id).where(article_tags.c.tag_id.in_(tag_ids))
        if match_all:
            subquery = subquery.group_by(article_tags.c.article_id).having(
                func.count(func.distinct(article_tags.c.tag_id)) == len(set(tag_ids))
            )

        return Article.id.in_(subquery)

    async def exists_visible(self, article_id: int, include_hidden: bool) -> bool:
        """Whether the article exists AND the reader may see it (drafts/GM-only count as missing for non-GMs)."""

        stmt = select(Article.id).where(Article.id == article_id, *self._visibility_conditions(include_hidden))
        return await self.db.scalar(stmt) is not None

    async def list_children(self, article_id: int, *, include_hidden: bool = False) -> list[Article]:
        """Return the direct children of ``article_id`` (one level down), ordered by title."""

        result = await self.db.execute(
            select(Article)
            .where(Article.parent_id == article_id, *self._visibility_conditions(include_hidden))
            .options(*self._brief_load_options())
            .order_by(Article.title)
        )
        return list(result.scalars().unique().all())

    async def list_descendants(self, article_id: int, *, include_hidden: bool = False) -> list[Article]:
        """
        Return every descendant of ``article_id`` at any depth (excluding itself), ordered by ``path``.

        For non-GM readers, a descendant only counts if every node strictly between
        ``article_id`` and it (exclusive of the root, inclusive of itself) is also
        visible — otherwise a hidden intermediate node's own visible descendants
        would leak through it.
        """

        parent_path = await self.db.scalar(select(Article.path).where(Article.id == article_id))
        if parent_path is None:
            return []

        conditions = [
            Article.path.op("<@")(parent_path),
            Article.id != article_id,
            *self._visibility_conditions(include_hidden),
        ]

        if not include_hidden:
            hidden_intermediate = aliased(Article)
            conditions.append(
                ~exists(
                    select(hidden_intermediate.id).where(
                        hidden_intermediate.path.op("<@")(parent_path),
                        hidden_intermediate.path.op("@>")(Article.path),
                        hidden_intermediate.id != article_id,
                        hidden_intermediate.id != Article.id,
                        or_(
                            hidden_intermediate.status != ArticleStatus.PUBLISHED,
                            hidden_intermediate.visibility != ArticleVisibility.PUBLIC,
                        ),
                    )
                )
            )

        result = await self.db.execute(
            select(Article)
            .where(and_(*conditions))
            .options(*self._brief_load_options())
            .order_by(Article.path)
        )
        return list(result.scalars().unique().all())

    async def list_ancestors(self, article_id: int, *, include_hidden: bool = False) -> list[Article]:
        """Return every ancestor of ``article_id`` (excluding itself), root-first."""

        child_path = await self.db.scalar(select(Article.path).where(Article.id == article_id))
        if child_path is None:
            return []

        result = await self.db.execute(
            select(Article)
            .where(
                Article.path.op("@>")(child_path),
                Article.id != article_id,
                *self._visibility_conditions(include_hidden),
            )
            .options(*self._brief_load_options())
            .order_by(Article.path)
        )
        return list(result.scalars().unique().all())

    async def list_articles(
        self,
        *,
        page: int,
        size: int,
        include_hidden: bool,
        statuses: list[ArticleStatus] | None = None,
        article_types: list[str] | None = None,
        subtype_ids: list[int] | None = None,
        tag_ids: list[int] | None = None,
        match_all_tags: bool = False,
        sort: str = "title",
    ) -> tuple[list[Any], int]:
        """Filtered, sorted, paginated listing rows (no tags/images loaded) plus the total match count."""

        conditions = self._visibility_conditions(include_hidden)
        if statuses:
            conditions.append(Article.status.in_(statuses))
        if article_types or subtype_ids:
            conditions.append(await self._type_condition(article_types or [], subtype_ids or []))
        if tag_ids:
            conditions.append(self._tag_condition(tag_ids, match_all_tags))

        order_by = {
            "title": [Article.title, Article.id],
            "newest": [text("COALESCE(articles.published_at, articles.created_at) DESC"), Article.id.desc()],
            "oldest": [text("COALESCE(articles.published_at, articles.created_at) ASC"), Article.id],
            "updated": [Article.updated_at.desc(), Article.id.desc()],
        }[sort]

        result = await self.db.execute(
            select(
                Article.id,
                Article.slug,
                Article.title,
                self._excerpt_column(include_hidden),
                Article.article_type,
                *self._subtype_columns(),
                Article.status,
                Article.visibility,
                func.count().over().label("total"),
            )
            .outerjoin(ArticleSubtype, ArticleSubtype.id == Article.subtype_id)
            .where(*conditions)
            .order_by(*order_by)
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = list(result.all())
        total = rows[0].total if rows else await self._count(Article, conditions)
        return rows, total or 0

    async def search_articles(
        self,
        query: str,
        *,
        page: int,
        size: int,
        include_hidden: bool,
        article_types: list[str] | None = None,
        subtype_ids: list[int] | None = None,
        tag_ids: list[int] | None = None,
        match_all_tags: bool = False,
    ) -> tuple[list[Any], int]:
        """
        Full-text + typo-tolerant title search, best match first.

        A row matches when its weighted search vector (Russian OR simple config, so
        both stemmed and literal terms hit) matches ``query``, or its title is trigram-word-similar
        to it (substring/prefix match, e.g. "Аур" against "Аурис, бог Солнца"). ``rank`` blends
        ``ts_rank`` with title similarity; ``snippet`` is a ``ts_headline`` fragment of
        title/excerpt/body combined and wrapped in ``<mark>`` (rest of the text is raw markdown).

        Non-GM readers search ``search_vector`` and get the excerpt and snippets with GM-only
        blocks stripped, so a secret can neither match nor show up in a snippet; GMs search
        ``search_vector_gm`` over the full body.
        """

        russian_query = func.websearch_to_tsquery(RUSSIAN_CONFIG, query)
        combined_query = russian_query.op("||")(func.websearch_to_tsquery(SIMPLE_CONFIG, query))
        similarity = func.word_similarity(query, Article.title)
        #: Indexed (``gin_trgm_ops``) equivalent of ``word_similarity(query, title) > threshold``.
        title_match = Article.title.op("%>")(query)

        if include_hidden:
            vector, body = Article.search_vector_gm, Article.body_markdown
        else:
            vector = Article.search_vector
            body = func.regexp_replace(Article.body_markdown, ARTICLE_GM_BLOCK_SQL_PATTERN, " ", "g")

        excerpt = func.coalesce(self._excerpt_column(include_hidden), "")
        snippet_source = func.concat_ws(" ", Article.title, excerpt, body)

        conditions = [
            or_(vector.op("@@")(combined_query), title_match),
            *self._visibility_conditions(include_hidden),
        ]
        if article_types or subtype_ids:
            conditions.append(await self._type_condition(article_types or [], subtype_ids or []))
        if tag_ids:
            conditions.append(self._tag_condition(tag_ids, match_all_tags))

        rank = (func.ts_rank(vector, combined_query) + similarity).label("rank")
        snippet = func.ts_headline(
            RUSSIAN_CONFIG,
            snippet_source,
            combined_query,
            "StartSel=<mark>, StopSel=</mark>, MaxFragments=2, MaxWords=25, MinWords=10, ShortWord=2",
        ).label("snippet")

        # SET LOCAL rejects bind params; TITLE_SIMILARITY_THRESHOLD is a hardcoded constant, so inlining it is safe.
        await self.db.execute(text(f"SET LOCAL pg_trgm.word_similarity_threshold = {TITLE_SIMILARITY_THRESHOLD}"))
        result = await self.db.execute(
            select(
                Article.id,
                Article.slug,
                Article.title,
                self._excerpt_column(include_hidden),
                Article.article_type,
                *self._subtype_columns(),
                Article.status,
                Article.visibility,
                rank,
                snippet,
                func.count().over().label("total"),
            )
            .outerjoin(ArticleSubtype, ArticleSubtype.id == Article.subtype_id)
            .where(*conditions)
            .order_by(rank.desc(), Article.id)
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = list(result.all())
        total = rows[0].total if rows else await self._count(Article, conditions)
        return rows, total or 0
