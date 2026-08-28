"""Race repository: base CRUD plus ability-bonus management and in-use guard."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.features.subraces.crud.repository import SubraceRepository
from app.models import Character
from app.models.race_association_models import RaceAbilityBonus
from app.models.race_model import Race
from app.models.subrace_model import Subrace


class RaceRepository(BaseRepository[Race]):
    """
    Race-specific repository built on :class:`BaseRepository`.

    ``ability_bonuses`` and ``granted_skills`` are always part of
    ``RaceResponse``, so they're wired up as ``default_load_options``
    rather than re-implemented here via a hand-rolled ``get_all`` override.
    ``subraces`` (with their own ability bonuses) are loaded the same way so
    ``RaceResponse`` can embed them without extra queries; subrace CRUD
    itself lives in ``app.features.races.subraces``.

    ``search_fields=["name"]`` pins free-text ``search`` (on the inherited
    ``get_all``/``get_brief``) to just ``name`` — without this, the base
    class's auto-detection would also search ``description`` (also a text
    column on ``Race``), which isn't the intended behavior here. ``size``
    stays available as an exact-match ``filters`` key, inherited unchanged.

    ``get_all`` and ``get_brief`` are *not* overridden here anymore: the
    base class's pagination + eager-loading (``default_load_options``) +
    exact-match ``filters`` + free-text ``search`` (``search_fields``)
    cover everything races need.

    Skill lookup and ``set_skills`` moved to
    ``app.features.races.skills.repository.RaceSkillsRepository`` (which
    inherits this one) when the capabilities were split into subpackages.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(
            Race,
            db,
            default_load_options=[
                selectinload(Race.ability_bonuses),
                selectinload(Race.granted_skills),
                selectinload(Race.subraces).selectinload(Subrace.ability_bonuses),
            ],
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )
        self._subraces = SubraceRepository(db)

    async def get_subrace(self, race_id: int, subrace_id: int) -> Subrace | None:
        """
        Fetch a subrace by its own id, scoped to ``race_id``.

        Subrace CRUD lives in ``app.features.races.subraces``; this is a
        thin read-only delegation kept for the characters subdomain, which
        holds a ``RaceRepository`` and still validates ``subrace_id``
        against ``race_id`` through it (returns ``None`` when missing or
        owned by another race).
        """

        subrace = await self._subraces.get_by_id(subrace_id)
        if subrace is None or subrace.race_id != race_id:
            return None

        return subrace

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
