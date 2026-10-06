"""Article images service: upload, GM listing, and delete of images embedded in article bodies."""

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage.service import IMAGE_MAX_BYTES, ImageStorageService
from app.features.articles.base import ArticleScopedService
from app.features.articles.cache import ARTICLE_CACHE_NAMESPACES, invalidate_articles
from app.features.articles.images.exceptions import ArticleImageLimitException, ArticleImageNotFoundException
from app.features.articles.images.repository import ArticleImagesRepository
from app.features.articles.images.schemas import ArticleImageResponse
from app.models.articles.article_image_model import ArticleImage

#: Gallery size cap per article.
MAX_IMAGES_PER_ARTICLE = 100


def storage_entity(article_id: int, storage_key: str) -> str:
    """Storage folder for one image: the article plus the row's unguessable ``storage_key``; the row id is the file."""

    return f"articles/{article_id}/{storage_key}"


class ArticleImagesService(ArticleScopedService):
    """
    Article images: unlike a race/class/subrace's single ``image_url``
    (one object per row, upsert-replaced — see ``EntityImageService``), an
    article can carry several images, each its own DB row and its own
    Supabase Storage object (``articles/{article_id}/{storage_key}/{image_id}.{ext}``).

    Images are shown only where ``body_markdown`` embeds them (``![alt](url)``),
    so there's no caption/order metadata and the list is a GM editor concern.
    """

    repository: ArticleImagesRepository

    cache_namespaces = ARTICLE_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession, storage: ImageStorageService):
        """Initialize the service with the images repository and the shared storage backend."""

        super().__init__(ArticleImagesRepository(db))
        self._storage = storage

    async def list_images(self, article_id: int) -> list[ArticleImageResponse]:
        """Return every image uploaded for the article, oldest first (GM editor)."""

        await self._exists_or_404(article_id)
        rows = await self.repository.list_images(article_id)
        return [ArticleImageResponse.model_validate(row) for row in rows]

    async def upload_image(self, article_id: int, image: UploadFile) -> ArticleImageResponse:
        """
        Upload a new image for the article.

        No database transaction is held across the network call: a short transaction commits a
        placeholder row (its id and key name the storage object), the file is uploaded with no
        connection checked out, and a second short transaction sets the public URL and schedules the
        article's cache purge. If the upload or the second step fails, the placeholder row and any object
        written are removed again, so no row with an empty ``image_url`` outlives the request. At most
        ``IMAGE_MAX_BYTES`` + 1 bytes of the file are read.

        Raises:
            RecordNotFoundError: no such article.
            ArticleImageLimitException: the article already holds ``MAX_IMAGES_PER_ARTICLE`` images.
            ImageUploadError: the file was rejected by storage (type/size; 400).
        """

        await self._exists_or_404(article_id)
        if await self.repository.count_images(article_id) >= MAX_IMAGES_PER_ARTICLE:
            raise ArticleImageLimitException(article_id, MAX_IMAGES_PER_ARTICLE)

        try:
            content = await image.read(IMAGE_MAX_BYTES + 1)
        finally:
            await image.close()

        async with self._atomic():
            row = await self.repository.create_placeholder(article_id)
        image_id, entity = row.id, storage_entity(article_id, row.storage_key)

        try:
            url = await self._storage.upload_image(entity, image_id, content, image.content_type or "")
            async with self._atomic():
                updated = await self.repository.set_image_url(article_id, image_id, url)
                if updated is None:
                    raise ArticleImageNotFoundException(article_id=article_id, image_id=image_id)
                await invalidate_articles(self.repository.db, article_id)
        except Exception:
            await self._storage.delete_image(entity, image_id)
            async with self._atomic():
                await self.repository.delete_image_by_id(image_id)
                await invalidate_articles(self.repository.db, article_id)
            raise

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
        entity = storage_entity(article_id, image_row.storage_key)
        async with self._atomic():
            await self.repository.delete_image_row(image_row)
            await invalidate_articles(self.repository.db, article_id)
        await self._storage.delete_image(entity, image_id)

    async def _get_image_or_404(self, article_id: int, image_id: int) -> ArticleImage:
        """Fetch an image scoped to the article, or raise ``ArticleImageNotFoundException``."""

        image_row = await self.repository.get_image(article_id, image_id)
        if not image_row:
            raise ArticleImageNotFoundException(article_id=article_id, image_id=image_id)

        return image_row
