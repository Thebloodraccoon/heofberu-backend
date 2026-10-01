"""Article repository: writes (slug allocation, status moves, ltree paths) and the read queries (tree, listing, search)."""

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from sqlalchemy import and_, delete, exists, func, literal_column, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, load_only
from sqlalchemy_utils import Ltree

from app.constants import ArticleStatus, ArticleVisibility
from app.core.exceptions import RecordAlreadyExistsError
from app.features.articles.base import ArticleScopedRepository
from app.features.articles.exceptions import ArticleTreeTooDeepException
from app.features.articles.secrets import gm_stripped_sql
from app.features.articles.slug import slugify
from app.features.articles.visibility import visibility_conditions
from app.models.articles.article_association_models import article_tags
from app.models.articles.article_image_model import ArticleImage
from app.models.articles.article_model import Article
from app.models.articles.article_subtype_model import ArticleSubtype

T = TypeVar("T")

#: Minimum ``pg_trgm`` word-similarity for a title to count as a typo/prefix-tolerant match.
#: ``word_similarity`` (vs. plain ``similarity``) looks for the best-matching *substring* of the
#: title rather than comparing whole strings, so a short prefix like "Аур" still matches inside a
#: longer title like "Аурис, бог Солнца".
TITLE_SIMILARITY_THRESHOLD = 0.4

#: Deepest supported article tree (an ltree holds at most 256 labels; real lore nests a handful of levels).
MAX_TREE_DEPTH = 32
#: Cap on the unpaginated tree/relation lists (children, descendants), so a hub article can't return a whole catalog.
TREE_LIST_LIMIT = 1000
#: Tries at a free slug before giving up when concurrent writers keep taking the candidate.
SLUG_ATTEMPTS = 5
#: Key of the transaction-scoped advisory lock serialising every change of the article tree.
TREE_LOCK_KEY = 0x41525443

# Inline ``regconfig`` literals: a bound parameter would be sent as varchar, which Postgres
# won't accept where the text-search functions expect a ``regconfig``.
RUSSIAN_CONFIG = literal_column("'russian'::regconfig")
SIMPLE_CONFIG = literal_column("'simple'::regconfig")

SNIPPET_OPTIONS = "StartSel=<mark>, StopSel=</mark>, MaxFragments=2, MaxWords=25, MinWords=10, ShortWord=2"


class ArticleRepository(ArticleScopedRepository):
    """
    Article repository with eager-loaded tags and gallery images.

    No ``check_in_use_on_delete``: deleting an article that's someone's
    ``parent_id`` just detaches its children (``ondelete="SET NULL"``, see
    ``app/models/articles/article_model.py``) instead of being blocked —
    unlike a race/class/skill, nothing downstream depends on an article
    existing.
    """

    def __init__(self, db: AsyncSession):
        """Initialize the repository with eager-loaded tags and images, searchable by title/slug, unique slug."""

        super().__init__(db, load_tags_and_images=True, search_fields=["title", "slug"], unique_fields=["slug"])

    async def get_write_state(self, article_id: int) -> Any:
        """Row ``(article_type, subtype_id, published_at, status)`` the write rules need, sans tags/images; ``None`` if absent."""

        result = await self.db.execute(
            select(Article.article_type, Article.subtype_id, Article.published_at, Article.status).where(
                Article.id == article_id
            )
        )
        return result.one_or_none()

    async def update_fields(self, article_id: int, fields: dict, *, commit: bool = True) -> None:
        """Write ``fields`` onto the article with one UPDATE (slug uniqueness checked), committing or flushing."""

        if fields:
            await self._check_uniqueness(fields, exclude_id=article_id)
            await self.db.execute(
                update(Article)
                .where(Article.id == article_id)
                .values(**fields)
                .execution_options(synchronize_session=False)
            )

        await self.commit_or_flush(commit=commit)

    async def transition_status(
        self, article_id: int, allowed_from: frozenset[ArticleStatus], target: ArticleStatus, *, reviewer_id: int | None
    ) -> bool:
        """
        Move the article to ``target`` only if it is currently in ``allowed_from`` (compare-and-set in one UPDATE).

        Returns whether a row moved, so two concurrent actions can't both pass a stale status check. A first
        publish stamps ``published_at``; ``reviewer_id`` is recorded when given.
        """

        values: dict[str, Any] = {"status": target}
        if reviewer_id is not None:
            values["reviewed_by_id"] = reviewer_id
        if target == ArticleStatus.PUBLISHED:
            values["published_at"] = func.coalesce(Article.published_at, func.now())

        result = await self.db.execute(
            update(Article)
            .where(Article.id == article_id, Article.status.in_(sorted(allowed_from, key=lambda s: s.value)))
            .values(**values)
            .returning(Article.id)
            .execution_options(synchronize_session=False)
        )
        return result.scalar_one_or_none() is not None

    async def delete_row(self, article_id: int) -> bool:
        """Delete the article row with one statement (tags, relations and images go with it by FK cascade)."""

        result = await self.db.execute(
            delete(Article).where(Article.id == article_id).execution_options(synchronize_session=False)
        )
        return bool(result.rowcount)

    async def generate_unique_slug(self, title: str, *, exclude_id: int | None = None) -> str:
        """
        Build a slug from ``title`` that no article uses yet: ``base``, then ``base-2``, ``base-3``, ...

        ``exclude_id`` ignores that article's own current slug (re-slugging on rename). Concurrent
        writers can still pick the same value; ``write_with_unique_slug`` retries on that.
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

    async def write_with_unique_slug(
        self, title: str, write: Callable[[str], Awaitable[T]], *, exclude_id: int | None = None
    ) -> T:
        """
        Run ``write(slug)`` with a free slug, retrying with a fresh one when a concurrent writer took it first.

        Each attempt runs in its own savepoint, so a lost race rolls back only that attempt and the
        enclosing transaction stays usable. ``write`` must flush so the unique constraint fires here.
        """

        slug = ""
        for _ in range(SLUG_ATTEMPTS):
            slug = await self.generate_unique_slug(title, exclude_id=exclude_id)
            try:
                async with self.db.begin_nested():
                    return await write(slug)
            except RecordAlreadyExistsError:
                continue
            except IntegrityError as exc:
                if "slug" not in str(exc.orig).lower():
                    raise

        raise RecordAlreadyExistsError(model_name="Article", field="slug", value=slug)

    async def lock_tree(self) -> None:
        """
        Serialise tree changes (create under a parent, re-parent, delete) until the transaction ends.

        Cycle checks and path rewrites read other rows' paths, so two concurrent moves (A under B, B under A)
        would each pass the check and together form a cycle; one global lock is enough for how rarely lore moves.
        """

        await self.db.execute(select(func.pg_advisory_xact_lock(TREE_LOCK_KEY)))

    async def _ancestor_chain(self, article_id: int) -> list[int]:
        """Ids from the root down to ``article_id`` (inclusive), walking ``parent_id`` (does not trust ``path``)."""

        chain = (
            select(Article.id, Article.parent_id, literal_column("1").label("depth"))
            .where(Article.id == article_id)
            .cte("chain", recursive=True)
        )
        step = (
            select(Article.id, Article.parent_id, (chain.c.depth + 1).label("depth"))
            .join(chain, Article.id == chain.c.parent_id)
            .where(chain.c.depth < 256)
        )
        chain = chain.union_all(step)

        result = await self.db.execute(select(chain.c.id).order_by(chain.c.depth.desc()))
        return list(result.scalars().all())

    async def is_self_or_descendant(self, article_id: int, candidate_id: int) -> bool:
        """Return whether ``candidate_id`` is ``article_id`` itself or sits anywhere in its subtree."""

        if candidate_id == article_id:
            return True

        return article_id in await self._ancestor_chain(candidate_id)

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

    async def set_path(self, article_id: int, parent_id: int | None, *, commit: bool = True) -> None:
        """
        Compute and persist ``path`` for ``article_id`` from its parent's ``path``.

        If the article already had a ``path`` (i.e. this is a re-parent, not
        the initial set on create), every existing descendant is re-rooted
        under the new path in the same statement (an ltree "move subtree")
        so ancestor/descendant queries stay correct for the whole subtree.
        A parent whose own ``path`` is missing is resolved through ``parent_id`` instead of
        silently making the article a root.

        Callers hold ``lock_tree`` and have rejected cycles first (see ``is_self_or_descendant``;
        ``ArticleCrudService`` does). Raises ``ArticleTreeTooDeepException`` past ``MAX_TREE_DEPTH``.
        """

        if parent_id is None:
            new_path = str(article_id)
        else:
            parent_path = await self.db.scalar(select(Article.path).where(Article.id == parent_id))
            if parent_path:
                new_path = f"{parent_path}.{article_id}"
            else:
                new_path = ".".join(str(node) for node in [*await self._ancestor_chain(parent_id), article_id])

        old_path = await self.db.scalar(select(Article.path).where(Article.id == article_id))

        height = 0
        if old_path:
            deepest = await self.db.scalar(
                select(func.max(func.nlevel(Article.path))).where(Article.path.op("<@")(old_path))
            )
            height = (deepest or 0) - len(str(old_path).split("."))
        if len(new_path.split(".")) + height > MAX_TREE_DEPTH:
            raise ArticleTreeTooDeepException(article_id, MAX_TREE_DEPTH)

        await self.db.execute(
            update(Article)
            .where(Article.id == article_id)
            .values(path=Ltree(new_path))
            .execution_options(synchronize_session=False)
        )

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

    async def detach_children(self, article_id: int) -> list[int]:
        """
        Re-root the whole subtree under ``article_id`` as if the article were already gone; return its direct children.

        Deleting an article only clears its children's ``parent_id`` (``ON DELETE SET NULL``); their ``path`` would
        keep pointing under the removed node. One UPDATE strips the article's prefix from every descendant's path.
        """

        result = await self.db.execute(select(Article.id).where(Article.parent_id == article_id))
        child_ids = list(result.scalars().all())
        if not child_ids:
            return child_ids

        path = await self.db.scalar(select(Article.path).where(Article.id == article_id))
        if path is None:
            for child_id in child_ids:
                await self.set_path(child_id, None, commit=False)
            return child_ids

        await self.db.execute(
            text(
                "UPDATE articles SET path = subpath(path, nlevel(CAST(:path AS ltree))) "
                "WHERE path <@ CAST(:path AS ltree) AND id != :article_id"
            ),
            {"path": str(path), "article_id": article_id},
        )
        return child_ids

    async def _count(self, model, conditions: list) -> int:
        """Fallback total for an empty page (``count() OVER()`` yields no row when nothing matches)."""

        return await self.db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0

    @staticmethod
    def _brief_load_options() -> list:
        """Columns an ``ArticleBrief`` response actually uses (tree endpoints don't need body/tags/images)."""

        return [load_only(Article.id, Article.slug, Article.title, Article.article_type, Article.subtype_id)]

    @staticmethod
    def _excerpt_column(include_hidden: bool):
        """``excerpt`` as the reader may see it: GM-only blocks stripped for non-GMs."""

        if include_hidden:
            return Article.excerpt

        return gm_stripped_sql(Article.excerpt).label("excerpt")

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

    async def _filter_conditions(
        self,
        include_hidden: bool,
        article_types: list[str] | None,
        subtype_ids: list[int] | None,
        tag_ids: list[int] | None,
        match_all_tags: bool,
    ) -> list:
        """Visibility plus the optional type/subtype/tag filters shared by the listing and the search."""

        conditions = visibility_conditions(include_hidden)
        if article_types or subtype_ids:
            conditions.append(await self._type_condition(article_types or [], subtype_ids or []))
        if tag_ids:
            conditions.append(self._tag_condition(tag_ids, match_all_tags))

        return conditions

    async def list_children(self, article_id: int, *, include_hidden: bool = False) -> list[Article]:
        """Return the direct children of ``article_id`` (one level down), ordered by title, at most ``TREE_LIST_LIMIT``."""

        result = await self.db.execute(
            select(Article)
            .where(Article.parent_id == article_id, *visibility_conditions(include_hidden))
            .options(*self._brief_load_options())
            .order_by(Article.title, Article.id)
            .limit(TREE_LIST_LIMIT)
        )
        return list(result.scalars().unique().all())

    async def list_descendants(self, article_id: int, *, include_hidden: bool = False) -> list[Article]:
        """
        Return the descendants of ``article_id`` at any depth (excluding itself), ordered by ``path``,
        at most ``TREE_LIST_LIMIT``.

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
            *visibility_conditions(include_hidden),
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
            .limit(TREE_LIST_LIMIT)
        )
        return list(result.scalars().unique().all())

    async def list_ancestors(self, article_id: int, *, include_hidden: bool = False) -> list[Article]:
        """Return every visible ancestor of ``article_id`` (excluding itself), root-first; a hidden one is skipped."""

        child_path = await self.db.scalar(select(Article.path).where(Article.id == article_id))
        if child_path is None:
            return []

        result = await self.db.execute(
            select(Article)
            .where(
                Article.path.op("@>")(child_path),
                Article.id != article_id,
                *visibility_conditions(include_hidden),
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

        conditions = await self._filter_conditions(include_hidden, article_types, subtype_ids, tag_ids, match_all_tags)
        if statuses:
            conditions.append(Article.status.in_(statuses))

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

        Ranking and paging run first over ids only; the expensive ``ts_headline`` is computed just for the
        returned page, not for every match.

        Non-GM readers search ``search_vector`` and get the excerpt and snippets with GM-only
        blocks stripped, so a secret can neither match nor show up in a snippet; GMs search
        ``search_vector_gm`` over the full body.
        """

        russian_query = func.websearch_to_tsquery(RUSSIAN_CONFIG, query)
        combined_query = russian_query.op("||")(func.websearch_to_tsquery(SIMPLE_CONFIG, query))
        title_match = Article.title.op("%>")(query)

        if include_hidden:
            vector, body = Article.search_vector_gm, Article.body_markdown
        else:
            vector, body = Article.search_vector, gm_stripped_sql(Article.body_markdown)

        conditions = [
            or_(vector.op("@@")(combined_query), title_match),
            *await self._filter_conditions(include_hidden, article_types, subtype_ids, tag_ids, match_all_tags),
        ]

        rank = (func.ts_rank(vector, combined_query) + func.word_similarity(query, Article.title)).label("rank")
        ranked_page = (
            select(Article.id.label("id"), rank, func.count().over().label("total"))
            .where(*conditions)
            .order_by(rank.desc(), Article.id)
            .offset((page - 1) * size)
            .limit(size)
            .subquery("ranked_page")
        )

        excerpt = func.coalesce(self._excerpt_column(include_hidden), "")
        snippet = func.ts_headline(
            RUSSIAN_CONFIG, func.concat_ws(" ", Article.title, excerpt, body), combined_query, SNIPPET_OPTIONS
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
                ranked_page.c.rank,
                snippet,
                ranked_page.c.total,
            )
            .join(ranked_page, ranked_page.c.id == Article.id)
            .outerjoin(ArticleSubtype, ArticleSubtype.id == Article.subtype_id)
            .order_by(ranked_page.c.rank.desc(), Article.id)
        )
        rows = list(result.all())
        total = rows[0].total if rows else await self._count(Article, conditions)
        return rows, total or 0
