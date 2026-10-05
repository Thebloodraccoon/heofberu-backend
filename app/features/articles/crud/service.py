"""Article CRUD: create, edit, restore a revision, delete, and the cached detail read (by id or slug)."""

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import is_article_publicly_visible
from app.core.base.service import BaseService
from app.core.cache import use_cache
from app.core.exceptions import RecordIdsInvalidError, RecordNotFoundError
from app.core.storage.service import ImageStorageService
from app.features.articles.access import ArticleActor
from app.features.articles.cache import (
    ARTICLE_CACHE_NAMESPACES,
    invalidate_all_articles,
    invalidate_article_trees,
    invalidate_articles,
)
from app.features.articles.crud.repository import ArticleRepository
from app.features.articles.crud.schemas import ArticleCreate, ArticleResponse, ArticleUpdate
from app.features.articles.crud.writer import ArticleWriter
from app.features.articles.images.service import storage_entity
from app.features.articles.revisions.repository import ArticleRevisionRepository
from app.features.articles.secrets import strip_gm_blocks
from app.features.articles.tree.repository import ArticleTreeRepository
from app.models.articles.article_model import Article

#: ``get_by_id`` cache lifetime: actively-edited lore shouldn't stay stale a full day (the platform default).
GET_BY_ID_TTL_SECONDS = 1800
#: Deleting an article with more direct children than this purges the namespace instead of listing every key.
MAX_POINT_INVALIDATIONS = 500


class ArticleCrudService(BaseService[Article, ArticleCreate, ArticleUpdate, ArticleResponse]):
    """
    Article lifecycle and detail reads.

    Editing policy: a GM edits only the articles they wrote (any status, a published one included, in place) and
    proposes changes to the rest (``articles.proposals``); the founder edits any article. An edit never changes
    ``status`` (only ``ArticleWorkflowService`` does). Every content change becomes a new version through
    ``ArticleWriter``.

    The detail payload is cached once per article (``get_by_id``, key ``cache.article_cache_key``) and masked per
    reader after the cache (``get_article`` / ``_reader_view``).
    """

    repository: ArticleRepository

    cache_namespaces = ARTICLE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession, storage: ImageStorageService | None = None):
        """Wire the repositories, the shared ``ArticleWriter`` and the storage used to clean up images on delete."""

        super().__init__(repository=ArticleRepository(db), response_schema=ArticleResponse)
        self.writer = ArticleWriter(db)
        self._tree = ArticleTreeRepository(db)
        self._revisions = ArticleRevisionRepository(db)
        self._storage = storage or ImageStorageService()

    @use_cache(ttl=GET_BY_ID_TTL_SECONDS)
    async def get_by_id(self, item_id: int) -> ArticleResponse:
        """The full article as a GM sees it, cached (see ``GET_BY_ID_TTL_SECONDS``); 404 if missing."""

        return await super().get_by_id(item_id)

    async def get_article(self, article_id: int, *, include_hidden: bool) -> ArticleResponse:
        """
        Detail read for any reader.

        GMs get the cached payload as is. Non-GMs first pass one live query (published + public, and whether the
        parent is visible), so a lost or late cache invalidation can never keep a withdrawn article public; then
        the cached payload is masked (``_reader_view``). Hidden articles 404 (never 403), so their existence isn't
        revealed.
        """

        if include_hidden:
            return await self.get_by_id(article_id)

        state = await self.repository.get_public_state(article_id=article_id)
        if state is None:
            raise RecordNotFoundError(model_name="Article", model_id=str(article_id))

        return await self._reader_view(state)

    async def get_article_by_slug(self, slug: str, *, include_hidden: bool) -> ArticleResponse:
        """``get_article`` looked up by ``slug``; the 404 names the slug, never the id (a hidden id must not leak)."""

        try:
            if include_hidden:
                article_id = await self.repository.get_id_by_slug(slug)
                if article_id is not None:
                    return await self.get_by_id(article_id)
            else:
                state = await self.repository.get_public_state(slug=slug)
                if state is not None:
                    return await self._reader_view(state)
        except RecordNotFoundError:
            pass
        raise RecordNotFoundError(model_name="Article", model_id=slug)

    async def _reader_view(self, state: Any) -> ArticleResponse:
        """
        The cached payload of a live-visible article (a ``get_public_state`` row), masked for a non-GM reader.

        * ``parent_id`` is nulled unless it is the parent the live check found visible (a hidden article's id
          must not leak through a public child);
        * ``:::gm`` blocks are stripped from ``body_markdown``/``excerpt``;
        * ``images`` is emptied: readers see images only where the stripped body embeds them;
        * ``version`` is hidden (readers always get the latest content).
        """

        article = await self.get_by_id(state.id)
        if not is_article_publicly_visible(article.status, article.visibility):
            raise RecordNotFoundError(model_name="Article", model_id=str(state.id))

        update: dict = {
            "body_markdown": strip_gm_blocks(article.body_markdown),
            "excerpt": strip_gm_blocks(article.excerpt),
            "images": [],
            "version": None,
        }
        if article.parent_id is not None and article.parent_id != state.visible_parent_id:
            update["parent_id"] = None

        return article.model_copy(update=update)

    async def create_article(self, data: ArticleCreate, author_id: int | None = None) -> ArticleResponse:
        """
        Create a draft from identity/content fields, stamped with its author; return it.

        The slug is generated from the title (a slug taken by a concurrent create is retried with the next free
        suffix), ``path`` is seeded from ``parent_id`` under the tree lock, and version 1 is recorded as the first
        revision. Tags and images are attached afterwards through their own endpoints.

        Raises:
            RecordIdsInvalidError: ``parent_id`` or ``subtype_id`` doesn't exist (400).
            ArticleSubtypeTypeMismatchException: the subtype belongs to another ``article_type`` (400).
        """

        await self.writer.validate_subtype(data.subtype_id, data.article_type)
        if data.parent_id is not None and not await self.repository.exists_by_id(data.parent_id):
            raise RecordIdsInvalidError(model_name="Article", ids=[data.parent_id])

        async def write(slug: str) -> Article:
            item = await self.repository.create({**data.model_dump(), "slug": slug, "author_id": author_id})
            await self._tree.set_path(item.id, data.parent_id)
            return item

        async with self._atomic():
            if data.parent_id is not None:
                await self._tree.lock_tree()
            item = await self.repository.write_with_unique_slug(data.title, write)
            await self.repository.record_revision(
                item.id, editor_id=author_id, reviewer_id=author_id, change_note=None, bump=False
            )
            await invalidate_article_trees(self.repository.db)

        return await self._get_response(item.id)

    async def update_article(self, article_id: int, data: ArticleUpdate, actor: ArticleActor) -> ArticleResponse:
        """
        Partially update an article (PATCH semantics) as its author or the founder; return it.

        Content changes become a new version reviewed by the editor themselves (like a direct push), with the
        optional ``change_note``; see ``ArticleWriter.apply_changes`` for moves, slugs and caching.

        Raises:
            RecordNotFoundError: no such article.
            ArticleEditForbiddenException: ``actor`` is neither the author nor the founder (403).
        """

        fields = data.model_dump(exclude_unset=True)
        change_note = fields.pop("change_note", None)
        state = await self.writer.write_state_or_404(article_id)
        actor.ensure_can_edit(article_id, state.author_id)

        return await self.writer.apply_changes(
            article_id, fields, state, editor_id=actor.id, reviewer_id=actor.id, change_note=change_note
        )

    async def restore_revision(self, article_id: int, version: int, actor: ArticleActor) -> ArticleResponse:
        """
        Make an old version's content current again, as a NEW version (history is never rewritten).

        Same edit rights as ``update_article``. Only content is restored: status, slug and position in the tree
        stay as they are. A subtype that has since been deleted or moved to another type is dropped.
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

    async def delete(self, item_id: int) -> bool:
        """
        Delete an article, then best-effort remove its images from storage.

        In one transaction under the tree lock: the children are detached (their subtrees re-rooted, since
        ``ON DELETE SET NULL`` only clears ``parent_id``) and the row is deleted (tags, relations, images cascade).
        After commit the article's and its children's cached payloads are dropped (the whole namespace past
        ``MAX_POINT_INVALIDATIONS`` children). Storage cleanup runs last, outside the transaction: Storage can't
        roll back, and ``ImageStorageService.delete_image`` logs failures instead of raising.

        Raises:
            RecordNotFoundError: no such article.
        """

        image_keys = await self.repository.list_image_keys(item_id)

        async with self._atomic():
            await self._tree.lock_tree()
            child_ids = await self._tree.detach_children(item_id)
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
