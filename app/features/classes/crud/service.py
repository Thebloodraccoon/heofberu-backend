"""Class CRUD service: cached catalog CRUD plus composed capability reads."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.cached_service import CachedService
from app.core.cache import use_cache
from app.features.classes.armor.service import ClassArmorService
from app.features.classes.cache import CLASS_CACHE_NAMESPACES, invalidate_class_cache
from app.features.classes.crud.repository import ClassRepository
from app.features.classes.features.service import ClassFeatureService
from app.features.classes.schemas import (
    ClassCreate,
    ClassFullResponse,
    ClassGetAllResponse,
    ClassResponse,
    ClassUpdate,
)
from app.features.classes.skills.service import ClassSkillService
from app.features.subclasses.crud.service import SubclassCrudService
from app.features.classes.throws.service import ClassThrowsService
from app.features.classes.weapons.service import ClassWeaponService
from app.models.class_model import Class


class ClassCrudService(CachedService[Class, ClassCreate, ClassUpdate, ClassResponse, ClassGetAllResponse]):
    """
    Class catalog CRUD built on :class:`CachedService`.

    Capability services are composed in ``__init__``: ``get_by_id`` reads
    CLASS-source ``features`` and a brief subclass reference;
    ``create_class`` seeds throws/proficiencies/skills in the same
    ``_atomic()`` transaction; subclass CRUD and subclass-feature
    endpoints delegate to ``self.subclasses``.
    """

    repository: ClassRepository

    cache_namespaces = CLASS_CACHE_NAMESPACES
    get_all_order_by = "name"

    def __init__(self, db: AsyncSession):
        """Initialize the service, composing the capability services."""

        super().__init__(
            repository=ClassRepository(db),
            response_schema=ClassResponse,
            get_all_schema=ClassGetAllResponse,
        )
        self._features = ClassFeatureService(db)
        self._skills = ClassSkillService(db)
        self._throws = ClassThrowsService(db)
        self._armor = ClassArmorService(db)
        self._weapons = ClassWeaponService(db)
        self.subclasses = SubclassCrudService(db)

    async def create_class(self, class_data: ClassCreate) -> ClassResponse:
        """
        Create a class with its scalar fields and simple child rows, atomically.

        Features, subclasses, spell slots, and starting items are NOT
        created here — attach them through their dedicated endpoints.
        """

        skills = await self._skills.resolve_skills(class_data.available_skills)

        payload = class_data.model_dump(
            exclude={
                "saving_throws",
                "armor_proficiencies",
                "weapon_proficiencies",
                "available_skills",
            }
        )

        async with self._atomic():
            item = await self.repository.create(payload, commit=False)

            if class_data.saving_throws:
                await self._throws.set_saving_throws_for_class(item, class_data.saving_throws, commit=False)

            if class_data.armor_proficiencies:
                await self._armor.set_armor_proficiencies_for_class(item, class_data.armor_proficiencies, commit=False)

            if class_data.weapon_proficiencies:
                await self._weapons.set_weapon_proficiencies_for_class(
                    item, class_data.weapon_proficiencies, commit=False
                )

            if skills:
                await self._skills.set_skills_for_class(item, skills, commit=False)

        await invalidate_class_cache()
        response = await self._get_response(item.id)

        # Warm the cache immediately so the next GET hits cache instead of
        # racing the invalidation into a cold read.
        await self.get_by_id(item.id)

        return response

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

        if update_data.armor_proficiencies is not None:
            character_class = await self._armor.set_armor_proficiencies_for_class(
                character_class, update_data.armor_proficiencies
            )

        if update_data.weapon_proficiencies is not None:
            await self._weapons.set_weapon_proficiencies_for_class(character_class, update_data.weapon_proficiencies)

        await invalidate_class_cache()
        response = await self._get_response(class_id)
        await self.get_by_id(class_id)

        return response

    @use_cache()
    async def get_by_id(self, item_id: int) -> ClassFullResponse:
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

        return ClassFullResponse.model_validate(
            {
                **ClassResponse.model_validate(character_class).model_dump(),
                "features": class_features,
                "subclasses": subclasses,
            }
        )
