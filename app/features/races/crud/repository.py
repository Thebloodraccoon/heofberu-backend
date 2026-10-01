"""Race repository: base CRUD plus ability-bonus management and in-use guard."""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base.repository import BaseRepository
from app.features.features.crud.repository import feature_summary_loads
from app.models.character.character_model import Character
from app.models.races.race_association_models import RaceAbilityBonus
from app.models.races.race_model import Race
from app.models.races.subrace_model import Subrace


class RaceRepository(BaseRepository[Race]):
    """Race repository with eager-loaded bonuses, skills, tags, features, and subraces."""

    def __init__(self, db: AsyncSession):
        """Initialize the repository with eager-loaded bonus, skill, tag, feature, and subrace fields."""

        super().__init__(
            Race,
            db,
            default_load_options=[
                selectinload(Race.ability_bonuses),
                selectinload(Race.granted_skills),
                selectinload(Race.tags),
                *feature_summary_loads(selectinload(Race.features)),
                selectinload(Race.subraces),
            ],
            search_fields=["name"],
            unique_fields=["name"],
            check_in_use_on_delete=True,
        )

    async def get_subrace(self, race_id: int, subrace_id: int) -> Subrace | None:
        """Fetch the bare subrace row, scoped to ``race_id``; ``None`` if missing or owned by another race."""

        return await self.db.scalar(select(Subrace).where(Subrace.id == subrace_id, Subrace.race_id == race_id))

    async def is_in_use(self, race_id: int) -> bool:
        """Whether a character uses this race or one of its subraces (blocks deletion)."""

        race_subraces = select(Subrace.id).where(Subrace.race_id == race_id)
        stmt = select(1).where(or_(Character.race_id == race_id, Character.subrace_id.in_(race_subraces))).limit(1)
        return await self.db.scalar(stmt) is not None

    async def list_subrace_ids(self, race_id: int) -> list[int]:
        """Ids of the race's subraces."""

        result = await self.db.execute(select(Subrace.id).where(Subrace.race_id == race_id))
        return list(result.scalars().all())

    async def set_ability_bonuses(self, race_id: int, bonuses: list[dict], *, commit: bool = True) -> None:
        """Replace all ability bonuses for a race with the given list."""

        await self.replace_child_rows(
            RaceAbilityBonus,
            Race(id=race_id),
            "race_id",
            bonuses,
            commit=commit,
        )
