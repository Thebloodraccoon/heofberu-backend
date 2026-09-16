"""Subclass repository: CRUD on ``Subclass`` rows, built on ``BaseRepository``."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.core.exceptions import RecordAlreadyExistsError
from app.features.features.crud.repository import feature_summary_loads
from app.models.character.character_model import Character
from app.models.classes.subclass_model import Subclass


class SubclassRepository(BaseRepository[Subclass]):
    """``BaseRepository``-backed repository for ``Subclass`` rows; ``class_id`` scoping is handled by the service layer."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with ``Subclass``'s search fields."""

        super().__init__(
            Subclass,
            db,
            default_load_options=feature_summary_loads(selectinload(Subclass.features)),
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

    async def list_for_class(self, class_id: int) -> list[Any]:
        """
        Return brief ``(id, class_id, name, image_url)`` rows for ``class_id``, ordered by name.

        Column-select on purpose: ``default_load_options`` eager-loads the
        full feature effect tree (``feature_summary_loads``), which
        ``SubclassGetAllResponse`` never uses — going through ``get_all``
        here would pay for that tree on every row of every listing.
        """

        return await self.get_brief(
            Subclass.id,
            Subclass.class_id,
            Subclass.name,
            Subclass.image_url,
            filters={"class_id": class_id},
            order_by=Subclass.name,
            limit=None,
        )
