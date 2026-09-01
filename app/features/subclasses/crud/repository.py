"""Subclass repository: CRUD on ``Subclass`` rows, built on ``BaseRepository``."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.repository import BaseRepository
from app.models.subclass_model import Subclass


class SubclassRepository(BaseRepository[Subclass]):
    """``BaseRepository``-backed repository for ``Subclass`` rows; ``class_id`` scoping is handled by the service layer."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with ``Subclass``'s search fields."""

        super().__init__(
            Subclass,
            db,
            search_fields=["name"],
        )

    async def list_for_class(self, class_id: int) -> list[Subclass]:
        """Return all subclasses for ``class_id``, ordered by name."""

        return await self.get_all(filters={"class_id": class_id}, order_by=Subclass.name, limit=None)
