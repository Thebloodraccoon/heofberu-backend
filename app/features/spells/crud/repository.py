"""Spell repository: base CRUD plus class/race availability management."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.models.class_model import Class
from app.models.race_model import Race
from app.models.spell_association_models import spell_classes, spell_races
from app.models.spell_model import Spell


class SpellRepository(BaseRepository[Spell]):
    """Spell-specific repository built on :class:`BaseRepository`."""

    def __init__(self, db: AsyncSession):
        super().__init__(
            Spell,
            db,
            default_load_options=[selectinload(Spell.available_classes), selectinload(Spell.available_races)],
            search_fields=["name"],
            unique_fields=["name"],
        )

    async def get_classes_by_ids(self, class_ids: list[int]) -> list[Class]:
        """Fetch the classes matching ``class_ids`` (order not guaranteed)."""

        return await self.get_many_by_ids(Class, class_ids)

    async def get_races_by_ids(self, race_ids: list[int]) -> list[Race]:
        """Fetch the races matching ``race_ids`` (order not guaranteed)."""

        return await self.get_many_by_ids(Race, race_ids)

    async def set_classes(self, spell: Spell, classes: list[Class], *, commit: bool = True) -> Spell:
        """
        Replace all classes a spell is available to.

        Written through the association table (delete + insert) instead of
        assigning the ORM ``available_classes`` relationship: assigning an
        unloaded many-to-many collection would trigger a lazy load, which
        is not supported on the async stack.

        ``commit`` lets callers that need atomicity across multiple writes
        (e.g. creating a spell + its class/race availability together)
        defer the commit and flush instead, without duplicating this
        method. See ``RaceRepository.set_ability_bonuses`` for the same
        pattern.
        """

        await self.replace_association(
            spell_classes,
            spell,
            "spell_id",
            "class_id",
            [class_.id for class_ in classes],
            commit=commit,
        )

        return spell

    async def set_races(self, spell: Spell, races: list[Race], *, commit: bool = True) -> Spell:
        """Replace all races a spell is available to. See ``set_classes`` for ``commit`` semantics."""

        await self.replace_association(
            spell_races,
            spell,
            "spell_id",
            "race_id",
            [race_.id for race_ in races],
            commit=commit,
        )

        return spell
