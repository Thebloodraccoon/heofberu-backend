"""Race repository: base CRUD plus ability-bonus management and in-use guard."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.features.subraces.crud.repository import SubraceRepository
from app.models import Character
from app.models.feature_model import Feature
from app.models.race_association_models import RaceAbilityBonus
from app.models.race_model import Race
from app.models.subrace_model import Subrace


class RaceRepository(BaseRepository[Race]):
    """Race repository with eager-loaded bonuses, skills, features, and subraces."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with eager-loaded bonus, skill, feature, and subrace fields."""

        super().__init__(
            Race,
            db,
            default_load_options=[
                selectinload(Race.ability_bonuses),
                selectinload(Race.granted_skills),
                selectinload(Race.features).selectinload(Feature.ability_increases),
                selectinload(Race.subraces).selectinload(Subrace.ability_bonuses),
            ],
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )
        self._subraces = SubraceRepository(db)

    async def get_subrace(self, race_id: int, subrace_id: int) -> Subrace | None:
        """Fetch a subrace by its own id, scoped to ``race_id``; returns ``None`` if missing or mismatched."""

        subrace = await self._subraces.get_by_id(subrace_id)
        if subrace is None or subrace.race_id != race_id:
            return None

        return subrace

    async def is_in_use(self, race_id: int) -> bool:
        """Check whether any character references this race (blocks deletion)."""

        return await self.exists_referencing(Character, "race_id", race_id)

    async def set_ability_bonuses(self, race: Race, bonuses: list[dict], *, commit: bool = True) -> Race:
        """Replace all ability bonuses for a race with the given list."""

        await self.replace_child_rows(
            RaceAbilityBonus,
            race,
            "race_id",
            bonuses,
            commit=commit,
        )

        return race
