"""Article images repository: per-article image listing, upload placeholder, delete."""

from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.articles.base import ArticleScopedRepository
from app.models.articles.article_image_model import ArticleImage


class ArticleImagesRepository(ArticleScopedRepository):
    """Image persistence for articles (the article lookups come from :class:`ArticleScopedRepository`)."""

    def __init__(self, db: AsyncSession):
        """Bind to ``Article`` without the tags/images eager loads (only image rows are touched here)."""

        super().__init__(db)

    async def list_images(self, article_id: int) -> list[ArticleImage]:
        """Return every image uploaded for the article, oldest first."""

        result = await self.db.execute(
            select(ArticleImage).where(ArticleImage.article_id == article_id).order_by(ArticleImage.id)
        )
        return list(result.scalars().all())

    async def count_images(self, article_id: int) -> int:
        """Return how many images the article holds."""

        return await self.db.scalar(select(func.count()).where(ArticleImage.article_id == article_id)) or 0

    async def get_image(self, article_id: int, image_id: int) -> ArticleImage | None:
        """Fetch a single image scoped to the article, or ``None``."""

        result = await self.db.execute(
            select(ArticleImage).where(
                ArticleImage.id == image_id,
                ArticleImage.article_id == article_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_placeholder(self, article_id: int) -> ArticleImage:
        """
        Insert an image row with an empty ``image_url`` and return it (id assigned).

        The row's id and fresh random ``storage_key`` form the storage object key
        (``articles/{article_id}/{storage_key}/{image_id}.{ext}``),
        so it has to exist before the upload happens — ``set_image_url`` fills
        ``image_url`` in once the upload succeeded.
        """

        row = ArticleImage(article_id=article_id, image_url="", storage_key=str(uuid4()))
        self.db.add(row)
        await self.flush()

        return row

    async def set_image_url(self, article_id: int, image_id: int, url: str) -> ArticleImage | None:
        """Persist the uploaded object's public URL onto the image row; ``None`` if the row vanished meanwhile."""

        image = await self.get_image(article_id, image_id)
        if image is None:
            return None

        image.image_url = url
        await self.flush()

        return image

    async def delete_image_by_id(self, image_id: int) -> None:
        """Remove an image row by id (a no-op when it is already gone)."""

        await self.db.execute(
            delete(ArticleImage).where(ArticleImage.id == image_id).execution_options(synchronize_session=False)
        )
        await self.flush()

    async def delete_image_row(self, image: ArticleImage) -> None:
        """Remove a single image row."""

        await self.db.delete(image)
        await self.flush()
