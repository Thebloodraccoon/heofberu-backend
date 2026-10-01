"""Subclass CRUD service: cached reads plus class-scoped writes."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.core.base.transaction import invalidate_after_commit
from app.core.cache import use_cache
from app.core.cache.client import cache_prefix
from app.core.exceptions import RecordNotFoundError
from app.features.classes.crud.repository import ClassRepository
from app.features.subclasses.cache import SUBCLASS_CRUD_CACHE_NAMESPACES, SUBCLASS_DELETE_CACHE_NAMESPACES
from app.features.subclasses.crud.repository import SubclassRepository
from app.features.subclasses.crud.schemas import (
    SubclassCreate,
    SubclassGetAllResponse,
    SubclassResponse,
    SubclassUpdate,
)
from app.models.classes.subclass_model import Subclass


class SubclassCrudService(
    BaseService[Subclass, SubclassCreate, SubclassUpdate, SubclassResponse, None],
):
    """
    Subclass catalog CRUD built on :class:`BaseService`.

    Subclasses belong to a class: creation 404s on an unknown ``class_id`` and
    name uniqueness is scoped to the class. ``get_by_id`` returns the subclass
    with its SUBCLASS-source features (written through the central features
    catalog). Every write purges ``SUBCLASS_CRUD_CACHE_NAMESPACES``.
    """

    repository: SubclassRepository

    cache_namespaces = SUBCLASS_CRUD_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize the service with its repository and a class repository for existence checks."""

        super().__init__(repository=SubclassRepository(db), response_schema=SubclassResponse)
        self._class_repository = ClassRepository(db)

    async def create_subclass(self, data: SubclassCreate) -> SubclassResponse:
        """Create a subclass for an existing class."""

        await self._ensure_class_exists(data.class_id)

        item = await self.repository.create(data.model_dump())
        await self._invalidate_cache()

        return await self.get_by_id(item.id)

    @use_cache(key_builder=lambda self, item_id: f"{cache_prefix()}:classes:subclass:get_by_id:{item_id}")
    async def get_by_id(self, item_id: int) -> SubclassResponse:
        """
        Return the subclass with its features (cached).

        The key differs from ``ClassCrudService.get_by_id`` (same namespace, other
        entity); every subclass write purges it through ``SUBCLASS_CRUD_CACHE_NAMESPACES``.
        """

        return await super().get_by_id(item_id)

    async def delete(self, item_id: int) -> bool:
        """Delete a subclass (blocked while characters use it); its cascaded features leave the cache too."""

        subclass = await self.repository.get_row(item_id)
        if subclass is None:
            raise RecordNotFoundError(model_name=Subclass.__name__, model_id=str(item_id))

        result = await self.repository.delete(subclass)
        await invalidate_after_commit(self.repository.db, *SUBCLASS_DELETE_CACHE_NAMESPACES)

        return result

    @use_cache(namespace="classes")
    async def list_for_class(self, class_id: int | None = None) -> list[SubclassGetAllResponse]:
        """Return brief subclass rows (cached), for one class or, without ``class_id``, for all; 404 for an unknown class."""

        if class_id is not None:
            await self._ensure_class_exists(class_id)

        rows = await self.repository.list_for_class(class_id)
        return [SubclassGetAllResponse.model_validate(row, from_attributes=True) for row in rows]

    async def _ensure_class_exists(self, class_id: int) -> None:
        """Raise ``RecordNotFoundError`` when no class with ``class_id`` exists."""

        if not await self._class_repository.exists_by_id(class_id):
            raise RecordNotFoundError(model_name="Class", model_id=str(class_id))
