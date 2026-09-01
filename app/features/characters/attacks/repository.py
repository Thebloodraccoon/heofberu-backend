"""Attack repository: character-scoped attack CRUD."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.repository import BaseRepository
from app.models.attack_model import Attack


class CharacterAttackRepository(BaseRepository[Attack]):
    """Repository for the ``Attack`` model, used by the attacks sub-domain (character-scoped CRUD)."""

    def __init__(self, db: AsyncSession):
        """Create the attack repository."""

        super().__init__(Attack, db)

    async def get_all_by_character(self, character_id: int) -> list[Attack]:
        """List a character's attacks, ordered by name."""

        result = await self.db.execute(select(Attack).where(Attack.character_id == character_id).order_by(Attack.name))
        return list(result.scalars().unique().all())

    async def get_by_id_and_character(self, attack_id: int, character_id: int) -> Attack | None:
        """Fetch an attack scoped to a character, or None if not present."""

        result = await self.db.execute(
            select(Attack).where(Attack.id == attack_id, Attack.character_id == character_id)
        )
        return result.scalar_one_or_none()
