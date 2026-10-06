"""GM max-HP repository: the single atomic write to ``characters.max_hp``."""

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.models.character.character_model import Character


class GmHpRepository:
    """Writes a character's maximum HP; the caller owns the transaction."""

    def __init__(self, db: AsyncSession):
        """Hold the session the write runs on."""

        self.db = db

    async def set_max_hp(self, character: Character, max_hp: int) -> None:
        """
        Set ``max_hp`` and clamp ``current_hp`` down to it in one statement,
        so a concurrent heal/damage on the same row is never overwritten with
        a stale value; the loaded ``character`` takes over the stored values.
        """

        result = await self.db.execute(
            update(Character)
            .where(Character.id == character.id)
            .values(max_hp=max_hp, current_hp=func.least(Character.current_hp, max_hp))
            .returning(Character.max_hp, Character.current_hp)
            .execution_options(synchronize_session=False)
        )
        stored_max_hp, stored_current_hp = result.one()
        set_committed_value(character, "max_hp", stored_max_hp)
        set_committed_value(character, "current_hp", stored_current_hp)
