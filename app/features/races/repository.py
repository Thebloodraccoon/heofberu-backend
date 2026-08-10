"""Race repository: base CRUD plus ability-bonus/skill management."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base_repository import BaseRepository
from app.features.skills.mixins import SkillLookupMixin
from app.models import Character
from app.models.race_association_models import RaceAbilityBonus, race_skills
from app.models.race_model import Race
from app.models.skill_model import Skill


class RaceRepository(SkillLookupMixin, BaseRepository[Race]):
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

        return await self.exists_referencing(Character, "race_id", race_id)

    async def set_ability_bonuses(self, race: Race, bonuses: list[dict], *, commit: bool = True) -> Race:
        """
        Replace all ability bonuses for a race with the given list.

        ``commit`` lets callers that need atomicity across multiple writes
        (e.g. creating a race + its bonuses + its skills together) defer
        the commit and flush instead, without duplicating this method.
        """

        await self.replace_child_rows(
            RaceAbilityBonus,
            race,
            "race_id",
            bonuses,
            commit=commit,
        )

        return race

    async def set_skills(self, race: Race, skills: list[Skill], *, commit: bool = True) -> Race:
        """
        Replace all granted skills for a race with the given list.

        Written through the association table (delete + insert) instead of
        assigning the ORM ``granted_skills`` relationship: assigning an
        unloaded many-to-many collection would trigger a lazy load, which
        is not supported on the async stack.

        See ``set_ability_bonuses`` for the meaning of ``commit=False``.
        """

        await self.replace_association(
            race_skills,
            race,
            "race_id",
            "skill_id",
            [skill.id for skill in skills],
            commit=commit,
        )

        return race
