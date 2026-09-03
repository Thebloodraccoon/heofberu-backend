"""Subclass repository: CRUD on ``Subclass`` rows, built on ``BaseRepository``."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.repository import BaseRepository
from app.core.exceptions import RecordAlreadyExistsError
from app.models.character_model import Character
from app.models.subclass_model import Subclass


class SubclassRepository(BaseRepository[Subclass]):
    """``BaseRepository``-backed repository for ``Subclass`` rows; ``class_id`` scoping is handled by the service layer."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with ``Subclass``'s search fields."""

        super().__init__(
            Subclass,
            db,
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    async def _check_uniqueness(self, data: dict[str, Any], exclude_id: int | None = None) -> None:
        """Raise ``RecordAlreadyExistsError`` if a sibling subclass with the same name already exists."""

        if not self._unique_fields:
            return

        for field in self._unique_fields:
            if field in data and data[field] is not None:
                value = data[field]
                stmt = select(self.model.id).where(getattr(self.model, field) == value)

                class_id = data.get("class_id")
                if class_id is not None:
                    stmt = stmt.where(self.model.class_id == class_id)

                if exclude_id is not None:
                    stmt = stmt.where(self.model.id != exclude_id)

                if await self.db.scalar(stmt) is not None:
                    raise RecordAlreadyExistsError(model_name=self.model.__name__, field=field, value=value)

    async def is_in_use(self, subclass_id: int) -> bool:
        """Check whether any character references this subclass (blocks deletion)."""

        return await self.exists_referencing(Character, "subclass_id", subclass_id)

    async def list_for_class(self, class_id: int) -> list[Subclass]:
        """Return all subclasses for ``class_id``, ordered by name."""

        return await self.get_all(filters={"class_id": class_id}, order_by=Subclass.name, limit=None)
