"""Character condition repository: active-condition row CRUD."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ConditionType
from app.core.base.repository import BaseRepository
from app.models.character_condition_model import CharacterCondition


class CharacterConditionRepository(BaseRepository[CharacterCondition]):
    """Repository for the conditions a character is currently under (``character_conditions``)."""

    def __init__(self, db: AsyncSession):
        """Create the condition repository."""

        super().__init__(CharacterCondition, db)

    async def get_character_conditions(self, character_id: int) -> list[CharacterCondition]:
        """Get every active condition on a character."""

        result = await self.db.execute(
            select(CharacterCondition).where(CharacterCondition.character_id == character_id)
        )
        return list(result.scalars().unique().all())

    async def get_character_condition(self, character_id: int, condition: ConditionType) -> CharacterCondition | None:
        """Fetch a character's active condition, if any."""

        result = await self.db.execute(
            select(CharacterCondition).where(
                CharacterCondition.character_id == character_id,
                CharacterCondition.condition == condition,
            )
        )
        return result.scalar_one_or_none()

    async def add_character_condition(
        self,
        character_id: int,
        condition: ConditionType,
        exhaustion_level: int | None,
        source: str,
    ) -> CharacterCondition:
        """Record an active condition on a character."""

        row = CharacterCondition(
            character_id=character_id,
            condition=condition,
            exhaustion_level=exhaustion_level,
            source=source,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)

        return row

    async def update_character_condition(
        self,
        row: CharacterCondition,
        update_data: dict[str, object],
    ) -> CharacterCondition:
        """Apply field updates onto an existing condition row."""

        for field, value in update_data.items():
            if hasattr(row, field):
                setattr(row, field, value)

        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def remove_character_condition(self, row: CharacterCondition) -> bool:
        """Remove an active condition from a character."""

        await self.db.delete(row)
        await self.db.commit()
        return True
