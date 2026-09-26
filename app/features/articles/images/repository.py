"""Article images repository: per-article image listing, upload placeholder, delete."""

from sqlalchemy import select

from app.features.articles.crud.repository import ArticleRepository
from app.models.articles.article_image_model import ArticleImage


class ArticleImagesRepository(ArticleRepository):
    """Image persistence for articles, layered on :class:`ArticleRepository`."""

    async def list_images(self, article_id: int) -> list[ArticleImage]:
        """Return every image uploaded for the article, oldest first."""

        result = await self.db.execute(
            select(ArticleImage).where(ArticleImage.article_id == article_id).order_by(ArticleImage.id)
        )
        return list(result.scalars().all())

    async def get_image(self, article_id: int, image_id: int) -> ArticleImage | None:
        """Fetch a single image scoped to the article, or ``None``."""

        result = await self.db.execute(
            select(ArticleImage).where(
                ArticleImage.id == image_id,
                ArticleImage.article_id == article_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_placeholder(self, article_id: int, *, commit: bool = True) -> ArticleImage:
        """
        Insert an image row with an empty ``image_url`` and return it (id assigned).

        The row's own id is the storage object key (``articles/{article_id}/{image_id}.{ext}``),
        so it has to exist before the upload happens — ``set_image_url`` fills
        ``image_url`` in immediately afterward.
        """

        row = ArticleImage(article_id=article_id, image_url="")
        self.db.add(row)
        await self.commit_or_flush(commit=commit)

        return row

    async def set_image_url(self, image: ArticleImage, url: str, *, commit: bool = True) -> ArticleImage:
        """Persist the uploaded object's public URL onto an existing image row."""

        image.image_url = url
        await self.commit_or_flush(commit=commit)

        return image

    async def delete_image_row(self, image: ArticleImage, *, commit: bool = True) -> None:
        """Remove a single image row."""

        await self.db.delete(image)
        await self.commit_or_flush(commit=commit)
