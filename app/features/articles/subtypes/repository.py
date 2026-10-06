"""Article subtype repository: base CRUD with per-type, case-insensitive name uniqueness."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.repository import BaseRepository
from app.core.exceptions import RecordAlreadyExistsError
from app.models.articles.article_subtype_model import ArticleSubtype


class ArticleSubtypeRepository(BaseRepository[ArticleSubtype]):
    """Subtype persistence built on :class:`BaseRepository`."""

    def __init__(self, db: AsyncSession):
        """Initialize the subtype repository (search by name)."""

        super().__init__(ArticleSubtype, db, search_fields=["name"])

    async def _check_uniqueness(self, data: dict[str, Any], exclude_id: int | None = None) -> None:
        """Raise ``RecordAlreadyExistsError`` if the ``article_type`` already has this name, ignoring case."""

        name = data.get("name")
        if name is None:
            return

        article_type = data.get("article_type")
        if article_type is None and exclude_id is not None:
            article_type = await self.db.scalar(
                select(ArticleSubtype.article_type).where(ArticleSubtype.id == exclude_id)
            )

        stmt = select(ArticleSubtype.id).where(
            ArticleSubtype.article_type == article_type, func.lower(ArticleSubtype.name) == name.lower()
        )
        if exclude_id is not None:
            stmt = stmt.where(ArticleSubtype.id != exclude_id)

        if await self.db.scalar(stmt) is not None:
            raise RecordAlreadyExistsError(model_name="ArticleSubtype", field="name", value=name)

    async def list_subtypes(self, article_type: str | None) -> list[ArticleSubtype]:
        """Every subtype (optionally of one ``article_type``), ordered by type then name."""

        stmt = select(ArticleSubtype).order_by(ArticleSubtype.article_type, func.lower(ArticleSubtype.name))
        if article_type is not None:
            stmt = stmt.where(ArticleSubtype.article_type == article_type)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())
