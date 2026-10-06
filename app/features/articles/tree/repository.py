"""
Article tree: ``parent_id`` plus a denormalised ltree ``path`` (``"12.40.41"``, root first).

Write primitives (lock, cycle check, path rewrite, detaching on delete) used by ``ArticleWriter`` and
``ArticleCrudService``, and the tree reads behind ``/articles/{id}/children|descendants|ancestors``.
"""

from sqlalchemy import and_, exists, func, literal_column, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, load_only, noload
from sqlalchemy_utils import Ltree

from app.constants import ArticleStatus, ArticleVisibility
from app.features.articles.base import ArticleScopedRepository
from app.features.articles.exceptions import ArticleTreeTooDeepException
from app.features.articles.visibility import visibility_conditions
from app.models.articles.article_model import Article

#: Deepest supported article tree (an ltree holds at most 256 labels; real lore nests a handful of levels).
MAX_TREE_DEPTH = 32
#: Cap on the unpaginated tree lists (children, descendants), so a hub article can't return a whole catalog.
TREE_LIST_LIMIT = 1000
#: Key of the transaction-scoped advisory lock serialising every change of the article tree.
TREE_LOCK_KEY = 0x41525443


class ArticleTreeRepository(ArticleScopedRepository):
    """Tree writes and reads over ``Article.parent_id`` / ``Article.path``."""

    def __init__(self, db: AsyncSession):
        """Bind to ``Article`` without the tags/images eager loads (tree rows are ``ArticleBrief``s)."""

        super().__init__(db)

    async def lock_tree(self) -> None:
        """
        Serialise tree changes (create under a parent, re-parent, delete) until the transaction ends.

        Cycle checks and path rewrites read other rows' paths, so two concurrent moves (A under B, B under A)
        would each pass the check and together form a cycle; one global lock is enough for how rarely lore moves.
        """

        # ponytail: one global lock; per-subtree locks if moves ever become frequent.
        await self.db.execute(select(func.pg_advisory_xact_lock(TREE_LOCK_KEY)))

    async def is_self_or_descendant(self, article_id: int, candidate_id: int) -> bool:
        """Whether ``candidate_id`` is ``article_id`` itself or sits anywhere in its subtree (i.e. would be a cycle)."""

        if candidate_id == article_id:
            return True

        return article_id in await self._ancestor_chain(candidate_id)

    async def set_path(self, article_id: int, parent_id: int | None) -> None:
        """
        Compute and persist ``path`` for ``article_id`` from its parent's ``path``.

        On a re-parent (the article already had a ``path``) every descendant is re-rooted under the new path in
        the same statement (an ltree "move subtree"). A parent whose own ``path`` is missing is resolved through
        ``parent_id`` instead of silently making the article a root.

        Callers hold ``lock_tree`` and have rejected cycles first (``is_self_or_descendant``).

        Raises:
            ArticleTreeTooDeepException: the move would nest the subtree deeper than ``MAX_TREE_DEPTH``.
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

        await self.flush()

    async def detach_children(self, article_id: int) -> list[int]:
        """
        Re-root the whole subtree under ``article_id`` as if the article were already gone; return its direct
        children's ids.

        Deleting an article only clears its children's ``parent_id`` (``ON DELETE SET NULL``); their ``path`` would
        keep pointing under the removed node. One UPDATE strips the article's prefix from every descendant's path.
        Call under ``lock_tree``, before deleting the row.
        """

        result = await self.db.execute(select(Article.id).where(Article.parent_id == article_id))
        child_ids = list(result.scalars().all())
        if not child_ids:
            return child_ids

        path = await self.db.scalar(select(Article.path).where(Article.id == article_id))
        if path is None:
            for child_id in child_ids:
                await self.set_path(child_id, None)
            return child_ids

        await self.db.execute(
            text(
                "UPDATE articles SET path = subpath(path, nlevel(CAST(:path AS ltree))) "
                "WHERE path <@ CAST(:path AS ltree) AND id != :article_id"
            ),
            {"path": str(path), "article_id": article_id},
        )
        return child_ids

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

    async def list_children(self, article_id: int, *, include_hidden: bool = False) -> list[Article]:
        """The direct children of ``article_id`` the reader may see, by title, at most ``TREE_LIST_LIMIT``."""

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
        The descendants of ``article_id`` at any depth (excluding itself), by ``path``, at most ``TREE_LIST_LIMIT``.

        For non-GM readers a descendant counts only if every node strictly between ``article_id`` and it is
        visible too; otherwise a hidden intermediate node's visible descendants would leak through it.
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
        """Every ancestor of ``article_id`` the reader may see (excluding itself), root first; hidden ones skipped."""

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

    @staticmethod
    def _brief_load_options() -> list:
        """
        Load only what an ``ArticleBrief`` uses: no body/tags/images and no joined ``author``.

        ``noload`` leaves ``author=None`` on these instances for the rest of the session; tree reads only run in
        GET requests, so no full ``ArticleResponse`` is built from the same instances.
        """

        return [
            load_only(Article.id, Article.slug, Article.title, Article.article_type, Article.subtype_id),
            noload(Article.author),
        ]
