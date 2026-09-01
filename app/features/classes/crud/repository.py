"""Class repository: base CRUD plus throws/spell-slot/subclass management."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models import (
    Character,
    Class,
    ClassArmorProficiency,
    ClassSavingThrow,
    ClassSpellSlotProgression,
    ClassWeaponProficiency,
    SourceItem,
)
from app.models.feature_model import Feature
from app.models.source_item_choice_model import SourceItemChoiceGroup, SourceItemChoiceOption
from app.models.subclass_model import Subclass


class ClassRepository(BaseRepository[Class]):
    """Class-specific repository built on :class:`BaseRepository` (skill management lives in ``ClassSkillsRepository``)."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with the class's default load options and search fields."""

        super().__init__(
            Class,
            db,
            default_load_options=[
                selectinload(Class.available_skills),
                selectinload(Class.saving_throws),
                selectinload(Class.armor_proficiencies),
                selectinload(Class.weapon_proficiencies),
                selectinload(Class.starting_items).selectinload(SourceItem.item),
                selectinload(Class.starting_choice_groups)
                .selectinload(SourceItemChoiceGroup.options)
                .selectinload(SourceItemChoiceOption.item),
                selectinload(Class.spell_slot_progression),
                selectinload(Class.subclasses),
            ],
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    async def is_in_use(self, class_id: int) -> bool:
        """Check whether any character references the class (blocks deletion via ON DELETE RESTRICT)."""

        return await self.exists_referencing(Character, "class_id", class_id)

    async def get_spell_slot_progression(self, class_id: int, class_level: int) -> dict[str, int]:
        """
        Return ``{spell_level: slots}`` for a single ``(class_id, class_level)``.

        Only levels with a ``ClassSpellSlotProgression`` row are included —
        a non-caster class returns ``{}``.
        """

        result = await self.db.execute(
            select(ClassSpellSlotProgression).where(
                ClassSpellSlotProgression.class_id == class_id,
                ClassSpellSlotProgression.class_level == class_level,
            )
        )
        rows = list(result.scalars().all())
        return {row.spell_level: row.slots for row in rows}

    async def set_spell_slots(
        self, character_class: Class, class_level: int, slots_by_spell_level: dict[str, int], *, commit: bool = True
    ) -> Class:
        """
        Replace spell slot rows for a single ``class_level``.

        Full replace: existing rows for this level are deleted first.
        """

        await self.replace_child_rows(
            ClassSpellSlotProgression,
            character_class,
            "class_id",
            [
                {"class_level": class_level, "spell_level": spell_level, "slots": slots}
                for spell_level, slots in slots_by_spell_level.items()
            ],
            extra_filters={"class_level": class_level},
            commit=commit,
        )

        return character_class

    async def set_saving_throws(self, character_class: Class, abilities: list[str], *, commit: bool = True) -> Class:
        """Replace all saving throw proficiencies for a class."""

        await self.replace_child_rows(
            ClassSavingThrow,
            character_class,
            "class_id",
            [{"ability": ability} for ability in abilities],
            commit=commit,
        )

        return character_class

    async def set_armor_proficiencies(
        self, character_class: Class, armor_types: list[str], *, commit: bool = True
    ) -> Class:
        """Replace all armor proficiencies for a class."""

        await self.replace_child_rows(
            ClassArmorProficiency,
            character_class,
            "class_id",
            [{"armor_type": armor_type} for armor_type in armor_types],
            commit=commit,
        )

        return character_class

    async def set_weapon_proficiencies(
        self, character_class: Class, weapon_categories: list[str], *, commit: bool = True
    ) -> Class:
        """Replace all weapon proficiencies for a class."""

        await self.replace_child_rows(
            ClassWeaponProficiency,
            character_class,
            "class_id",
            [{"weapon_category": weapon_category} for weapon_category in weapon_categories],
            commit=commit,
        )

        return character_class

    async def create_subclass(self, character_class: Class, payload: dict, *, commit: bool = True) -> Subclass:
        """
        Insert a ``Subclass`` row linked to ``character_class``.

        ``commit=False`` leaves the transaction open for the caller.
        """

        subclass = Subclass(**payload, class_id=character_class.id)
        self.db.add(subclass)
        if commit:
            await self.db.commit()
            await self.db.refresh(subclass)
        else:
            await self.db.flush()
        return subclass

    async def get_subclass(self, class_id: int, subclass_id: int) -> Subclass | None:
        """Fetch a subclass that belongs to ``class_id``, or ``None``."""

        result = await self.db.execute(
            select(Subclass)
            .where(Subclass.id == subclass_id, Subclass.class_id == class_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def list_subclasses(self, class_id: int) -> list[Subclass]:
        """Return all subclasses for ``class_id`` ordered by name."""

        result = await self.db.execute(
            select(Subclass)
            .where(Subclass.class_id == class_id)
            .order_by(Subclass.name)
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().unique().all())

    async def update_subclass(self, subclass: Subclass, fields: dict, *, commit: bool = True) -> Subclass:
        """Apply ``fields`` onto ``subclass`` and commit."""

        for field, value in fields.items():
            if hasattr(subclass, field):
                setattr(subclass, field, value)

        if commit:
            await self.db.commit()
            await self.db.refresh(subclass)
        else:
            await self.db.flush()

        return subclass

    async def delete_subclass(self, subclass: Subclass) -> None:
        """Delete a subclass (cascades to its features via ON DELETE CASCADE)."""

        await self.db.delete(subclass)
        await self.db.commit()

    async def get_progression_features(self, class_id: int) -> list[Feature]:
        """Return all CLASS and SUBCLASS features for ``class_id``, ordered by level."""

        subclass_ids = select(Subclass.id).where(Subclass.class_id == class_id)

        result = await self.db.execute(
            select(Feature)
            .where((Feature.class_id == class_id) | (Feature.subclass_id.in_(subclass_ids)))
            .order_by(Feature.level, Feature.id)
        )
        return list(result.scalars().unique().all())
