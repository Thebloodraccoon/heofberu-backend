"""Spell repository: base CRUD plus class/subclass/race/subrace availability management."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models import Class, Race, Spell, Subclass, Subrace
from app.models.spell_association_models import (
    spell_classes,
    spell_races,
    spell_subclasses,
    spell_subraces,
)


class SpellRepository(BaseRepository[Spell]):
    """Spell-specific repository built on :class:`BaseRepository`."""

    def __init__(self, db: AsyncSession):
        """Initialise with default load options and name uniqueness."""

        super().__init__(
            Spell,
            db,
            default_load_options=[
                selectinload(Spell.available_classes),
                selectinload(Spell.available_subclasses),
                selectinload(Spell.available_races),
                selectinload(Spell.available_subraces),
            ],
            search_fields=["name"],
            unique_fields=["name"],
        )

    async def get_classes_by_ids(self, class_ids: list[int]) -> list[Class]:
        """Fetch the classes matching ``class_ids`` (order not guaranteed)."""

        return await self.get_many_by_ids(Class, class_ids)

    async def get_subclasses_by_ids(self, subclass_ids: list[int]) -> list[Subclass]:
        """Fetch the subclasses matching ``subclass_ids`` (order not guaranteed)."""

        return await self.get_many_by_ids(Subclass, subclass_ids)

    async def get_races_by_ids(self, race_ids: list[int]) -> list[Race]:
        """Fetch the races matching ``race_ids`` (order not guaranteed)."""

        return await self.get_many_by_ids(Race, race_ids)

    async def get_subraces_by_ids(self, subrace_ids: list[int]) -> list[Subrace]:
        """Fetch the subraces matching ``subrace_ids`` (order not guaranteed)."""

        return await self.get_many_by_ids(Subrace, subrace_ids)

    async def set_classes(self, spell: Spell, classes: list[Class], *, commit: bool = True) -> Spell:
        """Replace all classes a spell is available to, via the association table to avoid a lazy load."""

        await self.replace_association(
            spell_classes,
            spell,
            "spell_id",
            "class_id",
            [class_.id for class_ in classes],
            commit=commit,
        )

        return spell

    async def set_subclasses(self, spell: Spell, subclasses: list[Subclass], *, commit: bool = True) -> Spell:
        """Replace all subclasses a spell is available to."""

        await self.replace_association(
            spell_subclasses,
            spell,
            "spell_id",
            "subclass_id",
            [subclass.id for subclass in subclasses],
            commit=commit,
        )

        return spell

    async def set_races(self, spell: Spell, races: list[Race], *, commit: bool = True) -> Spell:
        """Replace all races a spell is available to."""

        await self.replace_association(
            spell_races,
            spell,
            "spell_id",
            "race_id",
            [race_.id for race_ in races],
            commit=commit,
        )

        return spell

    async def set_subraces(self, spell: Spell, subraces: list[Subrace], *, commit: bool = True) -> Spell:
        """Replace all subraces a spell is available to."""

        await self.replace_association(
            spell_subraces,
            spell,
            "spell_id",
            "subrace_id",
            [subrace.id for subrace in subraces],
            commit=commit,
        )

        return spell
