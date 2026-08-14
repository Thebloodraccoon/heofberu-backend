"""Subclass repository: CRUD on ``Subclass`` rows, built on ``BaseRepository``."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.repository import BaseRepository
from app.models.subclass_model import Subclass


class SubclassRepository(BaseRepository[Subclass]):
    """
    ``BaseRepository``-backed repository for ``Subclass`` rows.

    Self-contained, same shape as ``ClassRepository``: ``get_by_id``,
    ``get_all``, ``create``, ``update``, ``delete`` all come straight from
    ``BaseRepository`` with no signature changes. ``class_id`` scoping
    (a subclass always belongs to exactly one class) is handled by the
    service layer via ``filters={"class_id": ...}`` / an explicit
    ownership check — the repository itself stays a plain single-model
    CRUD surface.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(
            Subclass,
            db,
            search_fields=["name"],
        )

    async def list_for_class(self, class_id: int) -> list[Subclass]:
        """Return all subclasses for ``class_id``, ordered by name."""

        return await self.get_all(filters={"class_id": class_id}, order_by=Subclass.name, limit=None)
