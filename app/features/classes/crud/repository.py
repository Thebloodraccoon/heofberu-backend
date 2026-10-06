"""Class repository: base CRUD plus child-row management, spell slots and the progression reads."""

from collections import namedtuple
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import DiceType
from app.core.base.repository import BaseRepository
from app.features.classes.proficiencies.kinds import ProficiencyKind
from app.features.features.crud.repository import feature_summary_loads
from app.features.shared.skills.mixins import SkillLookupMixin
from app.models import Character, Class, ClassSpellSlotProgression, SourceItem, class_available_skills
from app.models.classes.subclass_model import Subclass
from app.models.features.feature_model import Feature
from app.models.items.item_source_choice_model import SourceItemChoiceGroup, SourceItemChoiceOption
from app.models.skill_model import Skill

_ParentRef = namedtuple("_ParentRef", "id")


class ClassRepository(SkillLookupMixin, BaseRepository[Class]):
    """Class-specific repository built on :class:`BaseRepository`."""

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
                *feature_summary_loads(selectinload(Class.features)),
            ],
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    async def is_in_use(self, class_id: int) -> bool:
        """Check whether any character references the class (blocks deletion via ON DELETE RESTRICT)."""

        return await self.exists_referencing(Character, "class_id", class_id)

    async def get_row(self, class_id: int) -> Class | None:
        """Fetch the bare ``Class`` row (no relationships) for writes that only touch its own columns."""

        return await self.db.scalar(select(Class).where(Class.id == class_id).execution_options(populate_existing=True))

    async def get_name(self, class_id: int) -> str | None:
        """Return the class name, or ``None`` when the class does not exist."""

        return await self.db.scalar(select(Class.name).where(Class.id == class_id))

    async def get_hit_dice(self, class_id: int) -> DiceType | None:
        """Return the class hit dice, or ``None`` when the class does not exist."""

        return await self.db.scalar(select(Class.hit_dice).where(Class.id == class_id))

    async def get_character_ids(self, class_id: int) -> list[int]:
        """Ids of every character of the class (to purge their cached payloads)."""

        result = await self.db.execute(select(Character.id).where(Character.class_id == class_id))
        return list(result.scalars().all())

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
        return {row.spell_level: row.slots for row in result.scalars().all()}

    async def get_spell_slot_rows(self, class_id: int) -> list[ClassSpellSlotProgression]:
        """All spell slot rows of the class, ordered by class level then spell level."""

        result = await self.db.execute(
            select(ClassSpellSlotProgression)
            .where(ClassSpellSlotProgression.class_id == class_id)
            .order_by(ClassSpellSlotProgression.class_level, ClassSpellSlotProgression.spell_level)
        )
        return list(result.scalars().all())

    async def set_spell_slots(self, class_id: int, class_level: int, slots_by_spell_level: dict[str, int]) -> None:
        """Replace the spell slot rows of a single ``class_level`` (existing rows of that level are deleted first)."""

        await self.replace_child_rows(
            ClassSpellSlotProgression,
            _ParentRef(class_id),
            "class_id",
            [
                {"class_level": class_level, "spell_level": spell_level, "slots": slots}
                for spell_level, slots in slots_by_spell_level.items()
            ],
            extra_filters={"class_level": class_level},
        )

    async def set_proficiencies(self, class_id: int, kind: ProficiencyKind, values: list[Any]) -> None:
        """Replace one proficiency list (saving throws, armor or weapons) of the class."""

        await self.replace_child_rows(
            kind.model,
            _ParentRef(class_id),
            "class_id",
            [{kind.column: value} for value in values],
        )

    async def set_available_skills(self, class_id: int, skills: list[Skill] | None) -> None:
        """
        Replace all skills a class may choose proficiencies from.

        Written through the association table (delete + insert) instead of
        assigning the ORM relationship, which would trigger an unsupported
        lazy load on the async stack.
        """

        await self.replace_association(
            class_available_skills,
            _ParentRef(class_id),
            "class_id",
            "skill_id",
            [skill.id for skill in (skills or [])],
        )

    async def get_subclass(self, class_id: int, subclass_id: int) -> Subclass | None:
        """Fetch a subclass that belongs to ``class_id``, or ``None`` (used by the characters flows)."""

        result = await self.db.execute(
            select(Subclass)
            .where(Subclass.id == subclass_id, Subclass.class_id == class_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_progression_features(self, class_id: int) -> list[Feature]:
        """Return all CLASS and SUBCLASS features of ``class_id`` with their effect trees, ordered by level."""

        subclass_ids = select(Subclass.id).where(Subclass.class_id == class_id)

        result = await self.db.execute(
            select(Feature)
            .where((Feature.class_id == class_id) | (Feature.subclass_id.in_(subclass_ids)))
            .options(*feature_summary_loads())
            .order_by(Feature.level, Feature.id)
        )
        return list(result.scalars().unique().all())
