"""Article images service: upload, GM listing, and delete of images embedded in article bodies."""

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.core.storage.service import ImageStorageService
from app.features.articles.cache import ARTICLE_CACHE_NAMESPACES
from app.features.articles.crud.schemas import ArticleCreate, ArticleResponse, ArticleUpdate
from app.features.articles.images.exceptions import ArticleImageNotFoundException
from app.features.articles.images.repository import ArticleImagesRepository
from app.features.articles.images.schemas import ArticleImageResponse
from app.models.articles.article_image_model import ArticleImage
from app.models.articles.article_model import Article


def storage_entity(article_id: int) -> str:
    """Storage folder for one article's gallery — each image's own row id is the object key within it."""

    return f"articles/{article_id}"


class ArticleImagesService(BaseService[Article, ArticleCreate, ArticleUpdate, ArticleResponse, None]):
    """
    Article images: unlike a race/class/subrace's single ``image_url``
    (one object per row, upsert-replaced — see ``EntityImageService``), an
    article can carry several images, each its own DB row and its own
    Supabase Storage object (``articles/{article_id}/{image_id}.{ext}``).

    Images are shown only where ``body_markdown`` embeds them (``![alt](url)``),
    so there's no caption/order metadata and the list is a GM editor concern.
    """

    repository: ArticleImagesRepository

    cache_namespaces = ARTICLE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession, storage: ImageStorageService):
        """Initialize the service with the images repository and the shared storage backend."""

        super().__init__(
            repository=ArticleImagesRepository(db),
            response_schema=ArticleResponse,
        )
        self._storage = storage

    async def list_images(self, article_id: int) -> list[ArticleImageResponse]:
        """Return every image uploaded for the article, oldest first (GM editor)."""

        await self._exists_or_404(article_id)
        rows = await self.repository.list_images(article_id)
        return [ArticleImageResponse.model_validate(row) for row in rows]

    async def upload_image(self, article_id: int, image: UploadFile) -> ArticleImageResponse:
        """
        Upload a new image for the article.

        Reads the file first, then flushes (not commits) a placeholder row to
        get its id — the storage object key — uploads, and commits only once
        the public URL is set. A failure at any point rolls the placeholder
        back, so no row with an empty ``image_url`` is ever committed or
        visible to readers.
        """

        await self._exists_or_404(article_id)

        try:
            content = await image.read()
        finally:
            await image.close()

        row = await self.repository.create_placeholder(article_id, commit=False)
        image_id = row.id
        uploaded = False
        try:
            url = await self._storage.upload_image(
                storage_entity(article_id), image_id, content, image.content_type or ""
            )
            uploaded = True
            updated = await self.repository.set_image_url(row, url)
        except Exception:
            await self.repository.db.rollback()
            if uploaded:
                await self._storage.delete_image(storage_entity(article_id), image_id)
            raise

        await self._invalidate_cache()

        return ArticleImageResponse.model_validate(updated)

    async def delete_image(self, article_id: int, image_id: int) -> None:
        """
        Remove a single image of the article, in the DB and in storage.

        The DB row goes first: if that fails, the storage object is untouched and
        the image list stays consistent. Once the row is gone, the storage object is
        removed best-effort (``ImageStorageService.delete_image`` logs, never raises,
        so a storage-side failure can't leave the DB write half-applied).
        """

        await self._exists_or_404(article_id)
        image_row = await self._get_image_or_404(article_id, image_id)
        await self.repository.delete_image_row(image_row)
        await self._storage.delete_image(storage_entity(article_id), image_id)
        await self._invalidate_cache()

    async def _get_image_or_404(self, article_id: int, image_id: int) -> ArticleImage:
        """Fetch an image scoped to the article, or raise ``ArticleImageNotFoundException``."""

        image_row = await self.repository.get_image(article_id, image_id)
        if not image_row:
            raise ArticleImageNotFoundException(article_id=article_id, image_id=image_id)

        return image_row
