"""Class CRUD service: cached catalog CRUD plus composed capability reads."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.core.base.service import Page, paginate
from app.core.cache import use_cache
from app.features.classes.armor.service import ClassArmorService
from app.features.classes.cache import CLASS_CACHE_NAMESPACES, invalidate_class_cache
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.crud.schemas import (
    ClassCreate,
    ClassGetAllResponse,
    ClassResponse,
    ClassUpdate,
)
from app.features.classes.features.service import ClassFeatureService
from app.features.classes.throws.service import ClassThrowsService
from app.features.classes.weapons.service import ClassWeaponService
from app.features.subclasses.crud.schemas import SubclassGetAllResponse
from app.features.subclasses.crud.service import SubclassCrudService
from app.models.classes.class_model import Class
from app.models.classes.subclass_model import Subclass


class ClassCrudService(CachedService[Class, ClassCreate, ClassUpdate, ClassResponse, ClassGetAllResponse]):
    """
    Class catalog CRUD built on :class:`CachedService`.

    Capability services are composed in ``__init__``: ``get_by_id`` reads
    CLASS-source ``features`` and a brief subclass reference; ``_throws``/
    ``_armor``/``_weapons`` back ``update_class``'s full-replace PATCH
    fields; subclass CRUD and subclass-feature endpoints delegate to
    ``self.subclasses``. ``create_class`` writes base fields only — skills
    and proficiency lists are not seeded at create, see below.
    """

    repository: ClassRepository

    cache_namespaces = CLASS_CACHE_NAMESPACES

    def __init__(self, db: AsyncSession):
        """Initialize the service, composing the capability services."""

        super().__init__(
            repository=ClassRepository(db),
            response_schema=ClassResponse,
            get_all_schema=ClassGetAllResponse,
        )
        self._features = ClassFeatureService(db)
        self._throws = ClassThrowsService(db)
        self._armor = ClassArmorService(db)
        self._weapons = ClassWeaponService(db)
        self.subclasses = SubclassCrudService(db)

    async def create_class(self, class_data: ClassCreate) -> ClassResponse:
        """
        Create a class (base fields only).

        ``saving_throws``, ``armor_proficiencies``, ``weapon_proficiencies``,
        ``available_skills``, features, subclasses, spell slots, and
        starting items are not seeded here — each is attached afterwards
        through its own dedicated endpoint.
        """

        item = await self.repository.create(class_data.model_dump())
        await invalidate_class_cache()

        return await self.get_by_id(item.id)

    async def update_class(self, class_id: int, update_data: ClassUpdate) -> ClassResponse:
        """Partially update a class (PATCH semantics); the proficiency lists are full-replace when set."""

        character_class = await self._get_or_404(class_id)
        fields = update_data.model_dump(
            exclude_unset=True,
            exclude={"saving_throws", "armor_proficiencies", "weapon_proficiencies"},
        )

        if fields:
            character_class = await self.repository.update(character_class, fields)

        if update_data.saving_throws is not None:
            character_class = await self._throws.set_saving_throws_for_class(character_class, update_data.saving_throws)

        await invalidate_class_cache()

        return await self.get_by_id(class_id)

    @use_cache()
    async def get_all(
        self,
        page: int = 1,
        size: int = 100,
        filters: dict | None = None,
        search: str | None = None,
    ) -> Page[ClassGetAllResponse]:
        """
        Cached lightweight listing that avoids materializing full ``Class``
        rows: ``ClassGetAllResponse.subclasses`` is a relationship, which
        would otherwise fall back to ``repository.get_all``'s 9-chain
        ``default_load_options`` (proficiencies, choice groups, spell slot
        progression, the full feature effect tree) on every row.
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
            .order_by(Subclass.name)
        )
        rows = (await self.repository.db.execute(stmt)).all()

        result: dict[int, list[SubclassGetAllResponse]] = {}
        for row in rows:
            result.setdefault(row.class_id, []).append(SubclassGetAllResponse.model_validate(row))

        return result

    @use_cache()
    async def get_by_id(self, item_id: int) -> ClassResponse:
        """
        Return everything about a class in one payload: base fields,
        child rows, CLASS-source ``features``, and a brief reference to
        every subclass.

        Any write that touches this class (base fields, lists, features,
        subclasses, items, spell slots) invalidates the ``classes``
        namespace via ``cache_namespaces``.
        """

        character_class = await self._get_or_404(item_id)
        class_features = await self._features.list_features(item_id)
        subclasses = await self.subclasses.list_for_class(item_id)

        return ClassResponse.model_validate(
            {
                **ClassResponse.model_validate(character_class).model_dump(),
                "features": class_features,
                "subclasses": subclasses,
            }
        )
