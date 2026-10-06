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
    """``BaseRepository`` for ``Subclass`` rows; names are unique per class, not globally."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with ``Subclass``'s search fields."""

        super().__init__(
            Subclass,
            db,
            default_load_options=feature_summary_loads(selectinload(Subclass.features)),
            search_fields=["name"],
            check_in_use_on_delete=True,
        )

    def _uniqueness_scope(self, db_obj: Subclass) -> dict[str, Any]:
        """An update is checked against the siblings of the existing row's class."""

        return {"class_id": db_obj.class_id}

    async def _check_uniqueness(self, data: dict[str, Any], exclude_id: int | None = None) -> None:
        """Raise ``RecordAlreadyExistsError`` if a subclass with the same name exists (within ``data["class_id"]`` when given)."""

        name = data.get("name")
        if name is None:
            return

        stmt = select(Subclass.id).where(Subclass.name == name)
        if data.get("class_id") is not None:
            stmt = stmt.where(Subclass.class_id == data["class_id"])
        if exclude_id is not None:
            stmt = stmt.where(Subclass.id != exclude_id)

        if await self.db.scalar(stmt.limit(1)) is not None:
            raise RecordAlreadyExistsError(model_name=Subclass.__name__, field="name", value=name)

    async def is_in_use(self, subclass_id: int) -> bool:
        """Check whether any character references this subclass (blocks deletion)."""

        return await self.exists_referencing(Character, "subclass_id", subclass_id)

    async def get_row(self, subclass_id: int) -> Subclass | None:
        """Fetch the bare ``Subclass`` row (no feature tree) for writes that only touch its own columns."""

        return await self.db.scalar(
            select(Subclass).where(Subclass.id == subclass_id).execution_options(populate_existing=True)
        )

    async def list_for_class(self, class_id: int | None = None) -> list[Any]:
        """
        Return brief ``(id, class_id, name, image_url)`` rows ordered by name, optionally for one class.

        Column-select on purpose: ``default_load_options`` eager-loads the full
        feature effect tree, which ``SubclassGetAllResponse`` never uses.
        """

        return await self.get_brief(
            Subclass.id,
            Subclass.class_id,
            Subclass.name,
            Subclass.image_url,
            filters={"class_id": class_id} if class_id is not None else None,
            order_by=Subclass.name,
            limit=None,
        )
