"""Attack repository: character-scoped attack CRUD."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_repository import BaseRepository
from app.models.attack_model import Attack


class AttackRepository(BaseRepository[Attack]):
    """
    Repository for the ``Attack`` model. Used by the attacks sub-domain
    (CRUD).

    Inherits the base ``create`` unchanged — the service injects
    ``character_id`` into the create payload before calling it, mirroring
    how ``owner_id`` is injected for characters and ``created_by_id`` for
    races/classes/backgrounds (the old ``create(data, character_id)``
    signature override is gone).
    """

    def __init__(self, db: AsyncSession):
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
