"""``ArticleWriter``: the single write path for an article's fields."""

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.transaction import TransactionMixin
from app.core.exceptions import RecordIdsInvalidError, RecordNotFoundError
from app.features.articles.cache import TREE_PAYLOAD_FIELDS, invalidate_article_trees, invalidate_articles
from app.features.articles.crud.repository import REVISED_FIELDS, ArticleRepository
from app.features.articles.crud.schemas import ArticleResponse
from app.features.articles.exceptions import ArticleParentCycleException, ArticleSubtypeTypeMismatchException
from app.features.articles.tree.repository import ArticleTreeRepository


class ArticleWriter(TransactionMixin):
    """
    Writes already-authorized field changes to one article, in one transaction: subtype check, tree move, slug,
    version bump + revision snapshot, cache purge.

    Shared by ``ArticleCrudService`` (direct edits, revision restores) and ``ArticleProposalsService`` (accepted
    proposals), so both record history and purge caches the same way. It holds no permission rules and no
    storage: callers decide who may write before calling it.
    """

    def __init__(self, db: AsyncSession):
        """Bind the article and tree repositories to the request session."""

        self.repository = ArticleRepository(db)
        self.tree = ArticleTreeRepository(db)

    @property
    def _tx_db(self) -> AsyncSession:
        return self.repository.db

    async def write_state_or_404(self, article_id: int) -> Any:
        """The article's ``get_write_state`` row (type, subtype, published_at, status, author, version), or 404."""

        state = await self.repository.get_write_state(article_id)
        if state is None:
            raise RecordNotFoundError(model_name="Article", model_id=str(article_id))

        return state

    async def lock_version(self, article_id: int) -> int | None:
        """Lock the article row for the rest of the transaction and return its ``version`` (for ``guard``s)."""

        return await self.repository.lock_version(article_id)

    async def validate_subtype(self, subtype_id: int | None, article_type: str) -> None:
        """
        Reject a ``subtype_id`` that doesn't exist (400) or belongs to another ``article_type`` (400).

        ``None`` (no subtype) is always valid.
        """

        if subtype_id is None:
            return

        subtype_type = await self.repository.get_subtype_type(subtype_id)
        if subtype_type is None:
            raise RecordIdsInvalidError(model_name="ArticleSubtype", ids=[subtype_id])
        if subtype_type != article_type:
            raise ArticleSubtypeTypeMismatchException(subtype_id, subtype_type, article_type)

    async def validate_parent(self, parent_id: int | None, article_id: int) -> None:
        """
        Reject a ``parent_id`` that doesn't exist (400) or would make ``article_id`` its own ancestor (400).

        Call under ``ArticleTreeRepository.lock_tree`` so a concurrent move can't invalidate the check.
        """

        if parent_id is None:
            return

        if not await self.tree.exists_by_id(parent_id):
            raise RecordIdsInvalidError(model_name="Article", ids=[parent_id])

        if await self.tree.is_self_or_descendant(article_id, parent_id):
            raise ArticleParentCycleException(article_id=article_id, parent_id=parent_id)

    async def apply_changes(
        self,
        article_id: int,
        fields: dict,
        state: Any,
        *,
        editor_id: int | None,
        reviewer_id: int | None,
        change_note: str | None,
        guard: Callable[[], Awaitable[None]] | None = None,
    ) -> ArticleResponse:
        """
        Write ``fields`` (any of ``REVISED_FIELDS`` plus ``parent_id``) and return the updated article.

        Args:
            article_id: The article to change.
            fields: Column -> new value, already validated by the request schema (PATCH semantics: only these).
            state: The article's ``write_state_or_404`` row, read before the call.
            editor_id: Who wrote the change (recorded on the revision).
            reviewer_id: Who approved it (= ``editor_id`` for a direct edit; the acceptor for a proposal).
            change_note: Optional note stored with the new revision.
            guard: Runs first inside the transaction (lock + check a version, close a proposal); raising there
                rolls everything back.

        Behaviour:
            * a changed content field bumps ``version`` and snapshots a revision; a move alone does not;
            * ``parent_id`` re-roots the subtree under the tree lock, after the cycle check;
            * a new ``title`` re-generates the slug only while the article has never been published;
            * caches are purged after commit: the article's payload always, ``article_trees`` only when a field a
              tree/relation brief shows changed (``TREE_PAYLOAD_FIELDS``).
        """

        if "subtype_id" in fields or "article_type" in fields:
            await self.validate_subtype(
                fields.get("subtype_id", state.subtype_id), fields.get("article_type", state.article_type)
            )

        db = self.repository.db
        async with self._atomic():
            if guard is not None:
                await guard()

            if "parent_id" in fields:
                await self.tree.lock_tree()
                await self.validate_parent(fields["parent_id"], article_id)

            if "title" in fields and state.published_at is None:

                async def write(slug: str) -> None:
                    await self.repository.update_fields(article_id, {**fields, "slug": slug})

                await self.repository.write_with_unique_slug(fields["title"], write, exclude_id=article_id)
            else:
                await self.repository.update_fields(article_id, fields)

            if "parent_id" in fields:
                await self.tree.set_path(article_id, fields["parent_id"])

            if any(field in fields for field in REVISED_FIELDS):
                await self.repository.record_revision(
                    article_id, editor_id=editor_id, reviewer_id=reviewer_id, change_note=change_note, bump=True
                )

            await invalidate_articles(db, article_id)
            if not TREE_PAYLOAD_FIELDS.isdisjoint(fields):
                await invalidate_article_trees(db)

        return await self.response(article_id)

    async def response(self, article_id: int) -> ArticleResponse:
        """The article freshly read (tags and images loaded) as ``ArticleResponse``, or 404."""

        item = await self.repository.get_by_id(article_id)
        if item is None:
            raise RecordNotFoundError(model_name="Article", model_id=str(article_id))

        return ArticleResponse.model_validate(item)
