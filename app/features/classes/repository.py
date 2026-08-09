"""Class repository: base CRUD plus abilities/throws/skills/spell-slot/subclass management."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base_repository import BaseRepository
from app.models import Character, Class, ClassPrimaryAbility, ClassSavingThrow, ClassSpellSlotProgression, Skill
from app.models.feature_model import Feature
from app.models.subclass_model import Subclass


class ClassRepository(BaseRepository[Class]):
    """Class-specific repository built on :class:`BaseRepository`."""

    def __init__(self, db: AsyncSession):
        super().__init__(
            Class,
            db,
            default_load_options=[
                selectinload(Class.available_skills),
                selectinload(Class.primary_abilities),
                selectinload(Class.saving_throws),
                selectinload(Class.spell_slot_progression),
                selectinload(Class.features),
                selectinload(Class.subclasses).selectinload(Subclass.features),
            ],
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    async def is_in_use(self, class_id: int) -> bool:
        """
        Check whether the class is currently assigned to any character
        (characters.class_id), which would block deletion at the DB level
        via ON DELETE RESTRICT.
        """

        result = await self.db.execute(select(Character).where(Character.class_id == class_id))
        return result.scalar_one_or_none() is not None

    async def get_spell_slot_progression(self, class_id: int, class_level: int) -> dict[str, int]:
        """
        Return ``{spell_level: slots}`` for a single ``(class_id, class_level)`` pair.

        Only levels with an explicit ``ClassSpellSlotProgression`` row are
        included — a non-caster class (or a caster with no row for this
        level) simply returns ``{}``. Used by
        ``CharacterService`` to apply/refresh a character's actual spell
        slot totals whenever their level or class changes.
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

        await self.db.execute(
            delete(ClassSpellSlotProgression).where(
                ClassSpellSlotProgression.class_id == character_class.id,
                ClassSpellSlotProgression.class_level == class_level,
            )
        )

        for spell_level, slots in slots_by_spell_level.items():
            self.db.add(
                ClassSpellSlotProgression(
                    class_id=character_class.id,
                    class_level=class_level,
                    spell_level=spell_level,
                    slots=slots,
                )
            )

        if commit:
            await self.db.commit()
            await self.db.refresh(character_class)
        else:
            await self.db.flush()

        return character_class

    async def set_primary_abilities(self, character_class: Class, abilities: list[str], *, commit: bool = True) -> Class:
        """
        Replace all primary abilities for a class with the given list.

        ``commit`` lets callers that need atomicity across multiple writes
        (e.g. creating a class + its primary abilities + its saving throws
        together) defer the commit and flush instead, without duplicating
        this method.
        """

        await self.db.execute(delete(ClassPrimaryAbility).where(ClassPrimaryAbility.class_id == character_class.id))

        for ability in abilities:
            self.db.add(ClassPrimaryAbility(class_id=character_class.id, ability=ability))

        if commit:
            await self.db.commit()
            await self.db.refresh(character_class)
        else:
            await self.db.flush()

        return character_class

    async def set_saving_throws(self, character_class: Class, abilities: list[str], *, commit: bool = True) -> Class:
        """
        Replace all saving throw proficiencies for a class with the given list.

        See ``set_primary_abilities`` for the meaning of ``commit=False``.
        """

        await self.db.execute(delete(ClassSavingThrow).where(ClassSavingThrow.class_id == character_class.id))

        for ability in abilities:
            self.db.add(ClassSavingThrow(class_id=character_class.id, ability=ability))

        if commit:
            await self.db.commit()
            await self.db.refresh(character_class)
        else:
            await self.db.flush()

        return character_class

    async def get_skills_by_ids(self, skill_ids: list[int]) -> list[Skill]:
        """Fetch the skills matching ``skill_ids`` (order not guaranteed)."""

        if not skill_ids:
            return []

        result = await self.db.execute(select(Skill).where(Skill.id.in_(skill_ids)))
        return list(result.scalars().unique().all())

    async def set_available_skills(self, character_class: Class, skills: list[Skill], *, commit: bool = True) -> Class:
        """
        Replace all skills a class may choose proficiencies from.

        See ``set_primary_abilities`` for the meaning of ``commit=False``.
        """

        character_class.available_skills = skills

        if commit:
            await self.db.commit()
            await self.db.refresh(character_class)
        else:
            await self.db.flush()

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
            .options(selectinload(Subclass.features))
            .where(Subclass.id == subclass_id, Subclass.class_id == class_id)
        )
        return result.scalar_one_or_none()

    async def list_subclasses(self, class_id: int) -> list[Subclass]:
        """Return all subclasses for ``class_id`` ordered by name."""

        result = await self.db.execute(
            select(Subclass)
            .options(selectinload(Subclass.features))
            .where(Subclass.class_id == class_id)
            .order_by(Subclass.name)
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
        """
        Return all CLASS and SUBCLASS features for ``class_id``, ordered by level.
        Used to build the progression table in the service.
        """

        subclass_ids = select(Subclass.id).where(Subclass.class_id == class_id)

        result = await self.db.execute(
            select(Feature)
            .where(
                (Feature.class_id == class_id) | (Feature.subclass_id.in_(subclass_ids))
            )
            .order_by(Feature.level, Feature.id)
        )
        return list(result.scalars().unique().all())
