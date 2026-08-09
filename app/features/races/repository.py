"""Race repository: base CRUD plus ability-bonus/skill management."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base_repository import BaseRepository
from app.models import Character
from app.models.race_association_models import RaceAbilityBonus, race_skills
from app.models.race_model import Race
from app.models.skill_model import Skill


class RaceRepository(BaseRepository[Race]):
    """
    Race-specific repository built on :class:`BaseRepository`.

    ``ability_bonuses`` and ``granted_skills`` are always part of
    ``RaceResponse``, so they're wired up as ``default_load_options``
    rather than re-implemented here via a hand-rolled ``get_all`` override.

    ``search_fields=["name"]`` pins free-text ``search`` (on the inherited
    ``get_all``/``get_brief``) to just ``name`` — without this, the base
    class's auto-detection would also search ``description`` (also a text
    column on ``Race``), which isn't the intended behavior here. ``size``
    stays available as an exact-match ``filters`` key, inherited unchanged.

    ``get_all`` and ``get_brief`` are *not* overridden here anymore: the
    base class's pagination + eager-loading (``default_load_options``) +
    exact-match ``filters`` + free-text ``search`` (``search_fields``)
    cover everything races need.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(
            Race,
            db,
            default_load_options=[
                selectinload(Race.ability_bonuses),
                selectinload(Race.granted_skills),
                selectinload(Race.features),
            ],
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    async def is_in_use(self, race_id: int) -> bool:
        """
        Check whether the race is currently assigned to any character
        (characters.race_id), which would block deletion at the DB level
        via ON DELETE RESTRICT.
        """

        result = await self.db.execute(select(Character).where(Character.race_id == race_id))
        return result.scalar_one_or_none() is not None

    async def set_ability_bonuses(self, race: Race, bonuses: list[dict], *, commit: bool = True) -> Race:
        """
        Replace all ability bonuses for a race with the given list.

        ``commit`` lets callers that need atomicity across multiple writes
        (e.g. creating a race + its bonuses + its skills together) defer
        the commit and flush instead, without duplicating this method.
        """

        await self.db.execute(delete(RaceAbilityBonus).where(RaceAbilityBonus.race_id == race.id))

        for item in bonuses:
            self.db.add(RaceAbilityBonus(race_id=race.id, ability=item["ability"], bonus=item["bonus"]))

        if commit:
            await self.db.commit()
            await self.db.refresh(race)
        else:
            await self.db.flush()

        return race

    async def get_skills_by_ids(self, skill_ids: list[int]) -> list[Skill]:
        """Fetch the skills matching ``skill_ids`` (order not guaranteed)."""
        if not skill_ids:
            return []

        result = await self.db.execute(select(Skill).where(Skill.id.in_(skill_ids)))
        return list(result.scalars().unique().all())

    async def set_skills(self, race: Race, skills: list[Skill], *, commit: bool = True) -> Race:
        """
        Replace all granted skills for a race with the given list.

        Written through the association table (delete + insert) instead of
        assigning the ORM ``granted_skills`` relationship: assigning an
        unloaded many-to-many collection would trigger a lazy load, which
        is not supported on the async stack.

        See ``set_ability_bonuses`` for the meaning of ``commit=False``.
        """

        await self.db.execute(delete(race_skills).where(race_skills.c.race_id == race.id))

        if skills:
            await self.db.execute(
                race_skills.insert(),
                [{"race_id": race.id, "skill_id": skill.id} for skill in skills],
            )

        if commit:
            await self.db.commit()
            await self.db.refresh(race)
        else:
            await self.db.flush()

        return race
