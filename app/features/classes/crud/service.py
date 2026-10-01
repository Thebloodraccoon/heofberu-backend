"""Class CRUD service: cached catalog reads plus the class's own writes."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.core.base.service import Page, paginate
from app.core.base.transaction import invalidate_after_commit
from app.core.cache import use_cache
from app.core.exceptions import RecordNotFoundError
from app.features.characters.cache import invalidate_characters_cache
from app.features.classes.cache import CLASS_CRUD_CACHE_NAMESPACES, CLASS_DELETE_CACHE_NAMESPACES
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.crud.schemas import (
    ClassCreate,
    ClassGetAllResponse,
    ClassResponse,
    ClassUpdate,
)
from app.features.classes.proficiencies.kinds import SAVING_THROWS
from app.features.subclasses.crud.schemas import SubclassGetAllResponse
from app.models.classes.class_model import Class
from app.models.classes.subclass_model import Subclass


class ClassCrudService(CachedService[Class, ClassCreate, ClassUpdate, ClassResponse, ClassGetAllResponse]):
    """
    Class catalog CRUD built on :class:`CachedService`.

    ``get_by_id`` serializes the class with everything attached to it (child rows,
    CLASS-source features, brief subclasses) and is cached as one unit. Creation
    writes base fields only; every other aspect has its own endpoint.
    """

    repository: ClassRepository

    cache_namespaces = CLASS_CRUD_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize the service over the session."""

        super().__init__(
            repository=ClassRepository(db),
            response_schema=ClassResponse,
            get_all_schema=ClassGetAllResponse,
        )

    async def create_class(self, class_data: ClassCreate) -> ClassResponse:
        """Create a class (base fields only) and return it."""

        item = await self.repository.create(class_data.model_dump())
        await self._invalidate_cache()

        return await self.get_by_id(item.id)

    async def update_class(self, class_id: int, update_data: ClassUpdate) -> ClassResponse:
        """
        Partially update a class (PATCH semantics); ``saving_throws`` is a full replace when set.

        The row and the saving throws change in one transaction. Cached character
        payloads are purged only when ``hit_dice`` really changed (the one class
        value they derive live).
        """

        character_class = await self.repository.get_row(class_id)
        if character_class is None:
            raise RecordNotFoundError(model_name="Class", model_id=str(class_id))

        fields = update_data.model_dump(exclude_unset=True, exclude={"saving_throws"})
        hit_dice_changed = "hit_dice" in fields and fields["hit_dice"] != character_class.hit_dice

        async with self._unit_of_work() as uow:
            if fields:
                await self.repository.update(character_class, fields, commit=False)
            if update_data.saving_throws is not None:
                await self.repository.set_proficiencies(
                    class_id, SAVING_THROWS, update_data.saving_throws, commit=False
                )

            await uow.invalidate(*self.cache_namespaces)
            if hit_dice_changed:
                character_ids = await self.repository.get_character_ids(class_id)
                await uow.after_commit(lambda: invalidate_characters_cache(character_ids))

        return await self.get_by_id(class_id)

    async def delete(self, item_id: int) -> bool:
        """Delete a class (blocked while characters use it); cascaded subclasses/features/items leave the cache too."""

        character_class = await self.repository.get_row(item_id)
        if character_class is None:
            raise RecordNotFoundError(model_name="Class", model_id=str(item_id))

        result = await self.repository.delete(character_class)
        await invalidate_after_commit(self.repository.db, *CLASS_DELETE_CACHE_NAMESPACES)

        return result

    @use_cache()
    async def get_all(
        self,
        page: int = 1,
        size: int = 100,
        filters: dict | None = None,
        search: str | None = None,
    ) -> Page[ClassGetAllResponse]:
        """
        Cached lightweight listing (id, name, hit dice, image, brief subclasses).

        Selects columns instead of loading ``Class`` rows, which would drag the
        full ``default_load_options`` graph along for every row.
        """

        skip, limit = paginate(page, size)
        total = await self.repository.count(filters=filters, search=search)

        rows = await self.repository.get_brief(
            Class.id,
            Class.name,
            Class.hit_dice,
            Class.image_url,
            order_by=Class.name,
            skip=skip,
            limit=limit,
            filters=filters,
            search=search,
        )
        page_ids = [row.id for row in rows]
        subclasses = await self._load_subclasses(page_ids) if page_ids else {}

        items = [
            ClassGetAllResponse.model_validate({**row._mapping, "subclasses": subclasses.get(row.id, [])})
            for row in rows
        ]
        return Page(items=items, total=total, page=page, size=size)

    async def _load_subclasses(self, class_ids: list[int]) -> dict[int, list[SubclassGetAllResponse]]:
        """One brief query for every subclass under ``class_ids``, grouped by class id."""

        stmt = (
            select(Subclass.id, Subclass.class_id, Subclass.name, Subclass.image_url)
            .where(Subclass.class_id.in_(class_ids))
            .order_by(Subclass.name, Subclass.id)
        )
        rows = (await self.repository.db.execute(stmt)).all()

        result: dict[int, list[SubclassGetAllResponse]] = {}
        for row in rows:
            result.setdefault(row.class_id, []).append(SubclassGetAllResponse.model_validate(row))

        return result
