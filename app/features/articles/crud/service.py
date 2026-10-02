"""Article CRUD service: cached catalog CRUD plus composed capability reads."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ArticleStatus, is_article_publicly_visible
from app.core.base.cached_service import CachedService
from app.core.base.service import BaseService
from app.core.cache import use_cache
from app.core.exceptions import RecordIdsInvalidError, RecordNotFoundError
from app.core.pagination import CursorPage, Page, cursor_page, decode_cursor, paginate
from app.core.storage.service import ImageStorageService
from app.features.articles.access import ArticleActor
from app.features.articles.cache import (
    ARTICLE_CACHE_NAMESPACES,
    ARTICLE_TREE_NAMESPACE,
    invalidate_all_articles,
    invalidate_article_trees,
    invalidate_articles,
)
from app.features.articles.crud.repository import REVISED_FIELDS, ArticleRepository
from app.features.articles.crud.schemas import (
    ArticleBrief,
    ArticleCreate,
    ArticleGetAllResponse,
    ArticleResponse,
    ArticleSearchResult,
    ArticleUpdate,
)
from app.features.articles.exceptions import (
    ArticleParentCycleException,
    ArticleStatusTransitionException,
    ArticleSubtypeTypeMismatchException,
    ArticleVersionMismatchException,
)
from app.features.articles.images.service import storage_entity
from app.features.articles.revisions.repository import ArticleRevisionRepository
from app.features.articles.secrets import strip_gm_blocks
from app.models.articles.article_model import Article

ArticleAction = Literal["submit", "publish", "reject", "archive", "restore"]

#: Review workflow: action -> (statuses it's allowed from, resulting status). New articles start as DRAFT.
ARTICLE_TRANSITIONS: dict[ArticleAction, tuple[frozenset[ArticleStatus], ArticleStatus]] = {
    "submit": (frozenset({ArticleStatus.DRAFT}), ArticleStatus.IN_REVIEW),
    "publish": (frozenset({ArticleStatus.IN_REVIEW}), ArticleStatus.PUBLISHED),
    "reject": (frozenset({ArticleStatus.IN_REVIEW}), ArticleStatus.DRAFT),
    "archive": (
        frozenset({ArticleStatus.DRAFT, ArticleStatus.IN_REVIEW, ArticleStatus.PUBLISHED}),
        ArticleStatus.ARCHIVED,
    ),
    "restore": (frozenset({ArticleStatus.ARCHIVED}), ArticleStatus.DRAFT),
}

#: ``get_by_id`` cache lifetime: actively-edited lore shouldn't stay stale a full day (the platform default).
GET_BY_ID_TTL_SECONDS = 1800
#: Deleting an article with more direct children than this purges the namespace instead of listing every key.
MAX_POINT_INVALIDATIONS = 500


def _nest_row(row) -> dict:
    """Listing row (``subtype_*``/``author_username`` columns) -> dict with nested ``subtype``/``author`` objects."""

    data = dict(row._mapping)
    subtype_id, name = data.pop("subtype_id"), data.pop("subtype_name")
    data["subtype"] = {"id": subtype_id, "name": name} if subtype_id is not None else None
    author_id, username = data.pop("author_id"), data.pop("author_username")
    data["author"] = {"id": author_id, "username": username} if author_id is not None else None
    return data


class ArticleCrudService(
    CachedService[Article, ArticleCreate, ArticleUpdate, ArticleResponse, ArticleGetAllResponse],
):
    """
    Article catalog CRUD.

    Editing policy: a GM edits only the articles they wrote (any status, a published one included, in place) and
    proposes changes to the rest (``articles.proposals``); the founder edits any article. An edit never changes
    ``status`` (only the review actions do), so a published article stays published while it is edited. Every
    change of the content fields is recorded as a new version (``article_revisions``) and can be restored.
    """

    repository: ArticleRepository

    cache_namespaces = ARTICLE_CACHE_NAMESPACES
    get_all_order_by = "title"

    def __init__(self, db: AsyncSession, storage: ImageStorageService | None = None):
        """Initialize the article repository and the storage backend used to clean up gallery images on delete."""

        super().__init__(
            repository=ArticleRepository(db),
            response_schema=ArticleResponse,
            get_all_schema=ArticleGetAllResponse,
        )
        self._storage = storage or ImageStorageService()
        self._revisions = ArticleRevisionRepository(db)

    @use_cache(ttl=GET_BY_ID_TTL_SECONDS)
    async def get_by_id(self, item_id: int) -> ArticleResponse:
        """Cached fetch (see ``GET_BY_ID_TTL_SECONDS``); goes straight to ``BaseService`` so it is cached once, not twice."""

        return await BaseService.get_by_id(self, item_id)

    async def create_article(self, data: ArticleCreate, author_id: int | None = None) -> ArticleResponse:
        """
        Create an article (identity/content fields only), generate its slug from the title,
        stamp its author, and seed its ``path``.

        ``tags``/``images`` are not seeded here — attached afterwards through
        their own capability endpoints, mirroring ``RaceCrudService.create_race``.
        A slug taken by a concurrent create is retried with the next free suffix.
        """

        await self.validate_subtype(data.subtype_id, data.article_type)
        if data.parent_id is not None and not await self.repository.exists_by_id(data.parent_id):
            raise RecordIdsInvalidError(model_name="Article", ids=[data.parent_id])

        async def write(slug: str) -> Article:
            item = await self.repository.create(
                {**data.model_dump(), "slug": slug, "author_id": author_id}, commit=False
            )
            await self.repository.set_path(item.id, data.parent_id, commit=False)
            return item

        async with self._atomic():
            if data.parent_id is not None:
                await self.repository.lock_tree()
            item = await self.repository.write_with_unique_slug(data.title, write)
            await self.repository.record_revision(
                item.id, editor_id=author_id, reviewer_id=author_id, change_note=None, bump=False
            )
            await invalidate_article_trees(self.repository.db)

        return await self._get_response(item.id)

    async def update_article(self, article_id: int, data: ArticleUpdate, actor: ArticleActor) -> ArticleResponse:
        """
        Partially update an article; only its author or the founder may (403 for any other GM).

        A change of any content field (``REVISED_FIELDS``) bumps ``version`` and records a revision with the
        optional ``change_note``, reviewed by the editor themselves (like a direct push); a move (``parent_id``)
        alone is not a content change.

        Including ``parent_id`` re-roots ``path`` for the article and every
        existing descendant, and is rejected if it would create a cycle or
        point at a missing article; the cycle check and the rewrite run under one tree lock, so two
        concurrent moves can't together form a cycle. The field update and the path rewrite share
        one transaction. ``status`` never changes here — see ``transition``.

        A new ``title`` re-generates ``slug`` only while the article has never been
        published (like WordPress/Ghost drafts): once published the slug is its
        public address, so later renames keep it.
        """

        fields = data.model_dump(exclude_unset=True)
        change_note = fields.pop("change_note", None)
        state = await self.repository.get_write_state(article_id)
        if state is None:
            raise RecordNotFoundError(model_name="Article", model_id=str(article_id))
        actor.ensure_can_edit(article_id, state.author_id)

        return await self.apply_changes(
            article_id, fields, state, editor_id=actor.id, reviewer_id=actor.id, change_note=change_note
        )

    async def apply_changes(
        self,
        article_id: int,
        fields: dict,
        state,
        *,
        editor_id: int | None,
        reviewer_id: int | None,
        change_note: str | None,
        guard: Callable[[], Awaitable[None]] | None = None,
    ) -> ArticleResponse:
        """
        Write ``fields`` (already permission-checked) and record the revision as ``editor_id``/``reviewer_id``.

        ``state`` is the article's ``get_write_state`` row. ``guard`` runs first inside the transaction (e.g. lock
        the row and check the version, close a proposal); raising there rolls everything back.
        """

        if "subtype_id" in fields or "article_type" in fields:
            await self.validate_subtype(
                fields.get("subtype_id", state.subtype_id), fields.get("article_type", state.article_type)
            )

        async with self._atomic():
            if guard is not None:
                await guard()

            if "parent_id" in fields:
                await self.repository.lock_tree()
                await self._validate_parent(fields["parent_id"], article_id)

            if "title" in fields and state.published_at is None:

                async def write(slug: str) -> None:
                    await self.repository.update_fields(article_id, {**fields, "slug": slug}, commit=False)

                await self.repository.write_with_unique_slug(fields["title"], write, exclude_id=article_id)
            else:
                await self.repository.update_fields(article_id, fields, commit=False)

            if "parent_id" in fields:
                await self.repository.set_path(article_id, fields["parent_id"], commit=False)

            if any(field in fields for field in REVISED_FIELDS):
                await self.repository.record_revision(
                    article_id, editor_id=editor_id, reviewer_id=reviewer_id, change_note=change_note, bump=True
                )

            await invalidate_articles(self.repository.db, article_id)
            await invalidate_article_trees(self.repository.db)

        return await self._get_response(article_id)

    async def restore_revision(self, article_id: int, version: int, actor: ArticleActor) -> ArticleResponse:
        """
        Make an old version's content current again, as a NEW version (history is never rewritten).

        Same edit rights as ``update_article``. Only content is restored (see ``ArticleRevision``): status, slug and
        position in the tree stay as they are. A subtype that has since been deleted is dropped.
        """

        revision = await self._revisions.get(article_id, version)
        if revision is None:
            raise RecordNotFoundError(model_name="ArticleRevision", model_id=f"{article_id}@{version}")

        subtype_id = revision.subtype_id
        if subtype_id is not None and await self.repository.get_subtype_type(subtype_id) != revision.article_type:
            subtype_id = None

        data = ArticleUpdate(
            title=revision.title,
            excerpt=revision.excerpt,
            body_markdown=revision.body_markdown,
            article_type=revision.article_type,
            subtype_id=subtype_id,
            visibility=revision.visibility,
            change_note=f"Restored version {version}",
        )
        return await self.update_article(article_id, data, actor)

    async def transition(
        self, article_id: int, action: ArticleAction, *, actor: ArticleActor, expected_version: int | None = None
    ) -> ArticleResponse:
        """
        Apply a review-workflow ``action`` (see ``ARTICLE_TRANSITIONS``); 409 if the current status forbids it.

        The status check and the write are one conditional UPDATE, so concurrent actions can't both pass a
        stale check. ``actor`` is recorded as ``reviewed_by_id`` for ``publish``/``reject``; the first publish
        stamps ``published_at``. Only the author or the founder may ``submit``. ``publish`` takes the
        ``expected_version`` the founder reviewed and 409s if the article was edited since (so what gets published
        is exactly what was read).
        """

        allowed_from, target = ARTICLE_TRANSITIONS[action]

        if action == "submit":
            state = await self.repository.get_write_state(article_id)
            if state is None:
                raise RecordNotFoundError(model_name="Article", model_id=str(article_id))
            actor.ensure_can_edit(article_id, state.author_id)

        async with self._atomic():
            moved = await self.repository.transition_status(
                article_id,
                allowed_from,
                target,
                reviewer_id=actor.id if action in ("publish", "reject") else None,
                expected_version=expected_version,
            )
            if moved:
                await invalidate_articles(self.repository.db, article_id)
                await invalidate_article_trees(self.repository.db)

        if not moved:
            state = await self.repository.get_write_state(article_id)
            if state is None:
                raise RecordNotFoundError(model_name="Article", model_id=str(article_id))
            if ArticleStatus(state.status) in allowed_from and expected_version is not None:
                raise ArticleVersionMismatchException(article_id, expected_version, state.version)
            raise ArticleStatusTransitionException(article_id, action, ArticleStatus(state.status).value)

        return await self._get_response(article_id)

    async def delete(self, item_id: int) -> bool:
        """
        Delete an article, then best-effort remove its gallery images from storage.

        The row delete and the re-rooting of the children's subtrees share one ``_atomic()``
        transaction, so a failure partway through leaves nothing half-applied. Cache invalidation
        (the article's and its children's exact keys) runs after that transaction commits.

        Storage cleanup for gallery images runs last and outside the
        transaction — Storage knows nothing about Postgres rollback, so the
        DB write must have already succeeded before objects are removed (a
        storage failure is logged inside ``ImageStorageService.delete_image``,
        never raised).

        Direct children are detached, not deleted (``ondelete="SET NULL"``) —
        that FK action only clears their ``parent_id``, so their whole
        existing subtrees' ``path`` is re-rooted by one UPDATE in the same
        transaction, otherwise it would keep pointing under the deleted article's now-stale path.
        """

        image_keys = await self.repository.list_image_keys(item_id)

        async with self._atomic():
            await self.repository.lock_tree()
            child_ids = await self.repository.detach_children(item_id)
            if not await self.repository.delete_row(item_id):
                raise RecordNotFoundError(model_name="Article", model_id=str(item_id))

            if len(child_ids) > MAX_POINT_INVALIDATIONS:
                await invalidate_all_articles(self.repository.db)
            else:
                await invalidate_articles(self.repository.db, item_id, *child_ids)
                await invalidate_article_trees(self.repository.db)

        await asyncio.gather(
            *(self._storage.delete_image(storage_entity(item_id, key), image_id) for image_id, key in image_keys)
        )

        return True

    async def get_article(self, article_id: int, *, include_hidden: bool) -> ArticleResponse:
        """
        Cached detail read, with the visibility applied around the cache so one cached
        payload serves every reader: a non-GM first passes a live status/visibility check
        (a lost or late invalidation can never keep a withdrawn article public), then the
        cached payload is masked. Hidden articles 404 (not 403) for non-GMs, so their
        existence isn't revealed.

        ``parent_id`` is likewise nulled out for a non-GM reader when the parent
        itself isn't visible, so a hidden article's id/existence can't leak
        through a public child's detail response, GM-only ``:::gm`` blocks
        are stripped from ``body_markdown``/``excerpt``, ``images`` is emptied and ``version`` is hidden (readers only ever see the latest content).
        """

        if not include_hidden:
            await self._exists_visible_or_404(article_id, False)

        article = await self.get_by_id(article_id)
        if include_hidden:
            return article

        if not is_article_publicly_visible(article.status, article.visibility):
            raise RecordNotFoundError(model_name="Article", model_id=str(article_id))

        # Images reach readers only through ``![alt](url)`` in the (stripped) body; the raw
        # list would also leak ones placed inside :::gm blocks or not embedded at all.
        update: dict = {
            "body_markdown": strip_gm_blocks(article.body_markdown),
            "excerpt": strip_gm_blocks(article.excerpt),
            "images": [],
            "version": None,
        }
        if article.parent_id is not None and not await self.repository.exists_visible(article.parent_id, False):
            update["parent_id"] = None

        return article.model_copy(update=update)

    async def get_article_by_slug(self, slug: str, *, include_hidden: bool) -> ArticleResponse:
        """
        ``get_article`` looked up by ``slug``. The 404 names the slug, never the id, so a
        hidden article's id doesn't leak to a non-GM.
        """

        article_id = await self.repository.get_id_by_slug(slug)
        if article_id is not None:
            try:
                return await self.get_article(article_id, include_hidden=include_hidden)
            except RecordNotFoundError:
                pass
        raise RecordNotFoundError(model_name="Article", model_id=slug)

    async def list_articles(
        self,
        *,
        page: int,
        size: int,
        include_hidden: bool,
        statuses: list[ArticleStatus] | None,
        article_types: list[str] | None,
        subtype_ids: list[int] | None,
        tag_ids: list[int] | None,
        match_all_tags: bool,
        author_id: int | None = None,
        sort: str,
        cursor: str | None = None,
        use_cursor: bool = False,
        has_pending_proposals: bool | None = None,
    ) -> Page[ArticleGetAllResponse] | CursorPage[ArticleGetAllResponse]:
        """
        Filtered/sorted listing (not cached: results depend on the reader's visibility and the filters).

        ``has_pending_proposals`` (GM-only, ignored for other readers) keeps articles with / without a pending
        change proposal.

        Offset ``Page`` by default; with ``use_cursor`` a keyset ``CursorPage`` ordered by ``(sort key, id)``
        whose ``cursor`` must have been issued for the same ``sort``.
        """

        skip, limit = paginate(page, size)
        after = decode_cursor(cursor, sort, as_datetime=sort != "title") if cursor is not None else None
        rows, total = await self.repository.list_articles(
            skip=skip,
            limit=size + 1 if use_cursor else limit,
            include_hidden=include_hidden,
            statuses=statuses,
            article_types=article_types,
            subtype_ids=subtype_ids,
            tag_ids=tag_ids,
            match_all_tags=match_all_tags,
            author_id=author_id,
            has_pending_proposals=has_pending_proposals if include_hidden else None,
            sort=sort,
            after=after,
        )
        if use_cursor:
            rows, next_cursor = cursor_page(rows, size, sort, lambda row: (row.sort_value, row.id))
            items = [ArticleGetAllResponse.model_validate(_nest_row(row)) for row in rows]
            return CursorPage(items=items, next_cursor=next_cursor, size=size)

        items = [ArticleGetAllResponse.model_validate(_nest_row(row)) for row in rows]
        return Page(items=items, total=total, page=page, size=size)

    async def search_articles(
        self,
        query: str,
        *,
        page: int,
        size: int,
        include_hidden: bool,
        article_types: list[str] | None,
        subtype_ids: list[int] | None,
        tag_ids: list[int] | None,
        match_all_tags: bool,
        author_id: int | None = None,
        statuses: list[ArticleStatus] | None = None,
        has_pending_proposals: bool | None = None,
    ) -> Page[ArticleSearchResult]:
        """Ranked full-text search over visible articles; same filters as ``list_articles``."""

        skip, limit = paginate(page, size)
        rows, total = await self.repository.search_articles(
            query,
            skip=skip,
            limit=limit,
            include_hidden=include_hidden,
            article_types=article_types,
            subtype_ids=subtype_ids,
            tag_ids=tag_ids,
            match_all_tags=match_all_tags,
            author_id=author_id,
            statuses=statuses,
            has_pending_proposals=has_pending_proposals if include_hidden else None,
        )
        items = [ArticleSearchResult.model_validate(_nest_row(row)) for row in rows]
        return Page(items=items, total=total, page=page, size=size)

    async def get_children(self, article_id: int, *, include_hidden: bool) -> list[ArticleBrief]:
        """Return the direct children of an article. 404s if the article isn't visible to the reader."""

        await self._exists_visible_or_404(article_id, include_hidden)
        return await self._cached_children(article_id, include_hidden=include_hidden)

    @use_cache(namespace=ARTICLE_TREE_NAMESPACE)
    async def _cached_children(self, article_id: int, *, include_hidden: bool) -> list[ArticleBrief]:
        rows = await self.repository.list_children(article_id, include_hidden=include_hidden)
        return [ArticleBrief.model_validate(row) for row in rows]

    async def get_descendants(self, article_id: int, *, include_hidden: bool) -> list[ArticleBrief]:
        """Return the descendants of an article at any depth (capped, see the repository). 404s if it isn't visible."""

        await self._exists_visible_or_404(article_id, include_hidden)
        return await self._cached_descendants(article_id, include_hidden=include_hidden)

    @use_cache(namespace=ARTICLE_TREE_NAMESPACE)
    async def _cached_descendants(self, article_id: int, *, include_hidden: bool) -> list[ArticleBrief]:
        rows = await self.repository.list_descendants(article_id, include_hidden=include_hidden)
        return [ArticleBrief.model_validate(row) for row in rows]

    async def get_ancestors(self, article_id: int, *, include_hidden: bool) -> list[ArticleBrief]:
        """Return the breadcrumb chain (root-first) above an article. 404s if the article isn't visible."""

        await self._exists_visible_or_404(article_id, include_hidden)
        return await self._cached_ancestors(article_id, include_hidden=include_hidden)

    @use_cache(namespace=ARTICLE_TREE_NAMESPACE)
    async def _cached_ancestors(self, article_id: int, *, include_hidden: bool) -> list[ArticleBrief]:
        rows = await self.repository.list_ancestors(article_id, include_hidden=include_hidden)
        return [ArticleBrief.model_validate(row) for row in rows]

    async def _exists_visible_or_404(self, article_id: int, include_hidden: bool) -> None:
        """Raise ``RecordNotFoundError`` unless the article exists and the reader may see it."""

        if not await self.repository.exists_visible(article_id, include_hidden):
            raise RecordNotFoundError(model_name="Article", model_id=str(article_id))

    async def validate_subtype(self, subtype_id: int | None, article_type: str) -> None:
        """Reject a ``subtype_id`` that doesn't exist or belongs to another ``article_type`` (400)."""

        if subtype_id is None:
            return

        subtype_type = await self.repository.get_subtype_type(subtype_id)
        if subtype_type is None:
            raise RecordIdsInvalidError(model_name="ArticleSubtype", ids=[subtype_id])
        if subtype_type != article_type:
            raise ArticleSubtypeTypeMismatchException(subtype_id, subtype_type, article_type)

    async def _validate_parent(self, parent_id: int | None, article_id: int) -> None:
        """Reject a ``parent_id`` that doesn't exist or would make ``article_id`` its own ancestor (400)."""

        if parent_id is None:
            return

        if not await self.repository.exists_by_id(parent_id):
            raise RecordIdsInvalidError(model_name="Article", ids=[parent_id])

        if await self.repository.is_self_or_descendant(article_id, parent_id):
            raise ArticleParentCycleException(article_id=article_id, parent_id=parent_id)
