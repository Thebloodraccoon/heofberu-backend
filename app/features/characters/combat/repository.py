"""Queries behind the combat stats that no other character repository owns."""

from sqlalchemy import select

from app.core.base.repository import SessionRepository
from app.models.races.race_model import Race


class CombatRepository(SessionRepository):
    """Read-only lookups of the combat-stats computation."""

    async def race_name_and_speed(self, race_id: int | None) -> tuple[str, int] | None:
        """The race's name and walking speed, or ``None`` without a (still existing) race."""

        if race_id is None:
            return None

        row = (await self.db.execute(select(Race.name, Race.speed).where(Race.id == race_id))).first()
        return (row.name, row.speed) if row is not None else None
