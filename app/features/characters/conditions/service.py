"""Character condition service: managing active conditions on a character."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ConditionType
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.conditions.exceptions import (
    CharacterConditionAlreadyExistsException,
    CharacterConditionNotFoundException,
    InvalidConditionException,
)
from app.features.characters.conditions.repository import CharacterConditionRepository
from app.features.characters.conditions.schemas import (
    CharacterConditionAdd,
    CharacterConditionResponse,
    CharacterConditionUpdate,
)
from app.features.users.schemas import UserResponse
from app.models.character_condition_model import CharacterCondition


class CharacterConditionService(CharacterSubDomainService):
    """
    Manage the conditions a character is currently under
    (``character_conditions``).

    Uses two collaborators:
      - the inherited ``CharacterSubDomainService`` — access control
        only (fetching the owning character to check GM/owner permission
        via ``get_character_for_user``); no condition data lives there.
      - ``CharacterConditionRepository`` — the active-condition rows
        (CRUD).

    ``exhaustion_level`` follows 5e's rules: it is only meaningful (and
    therefore only accepted) when the condition is ``EXHAUSTION``, where
    it is required and must be between 1 and 6.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db)
        self.condition_repository = CharacterConditionRepository(db)

    async def get_conditions(
        self, character_id: int, current_user: UserResponse
    ) -> list[CharacterConditionResponse]:
        """List every condition a character is currently under."""

        await self.get_character_for_user(character_id, current_user)

        rows = await self.condition_repository.get_character_conditions(character_id)
        return [CharacterConditionResponse.model_validate(row) for row in rows]

    async def add_condition(
        self, character_id: int, data: CharacterConditionAdd, current_user: UserResponse
    ) -> CharacterConditionResponse:
        """Record an active condition on a character."""

        await self.get_character_for_user(character_id, current_user)

        existing = await self.condition_repository.get_character_condition(character_id, data.condition)
        if existing:
            raise CharacterConditionAlreadyExistsException(character_id=character_id, condition=data.condition)

        row = await self.condition_repository.add_character_condition(
            character_id,
            data.condition,
            data.exhaustion_level,
            data.source,
        )
        return CharacterConditionResponse.model_validate(row)

    async def update_condition(
        self,
        character_id: int,
        condition: ConditionType,
        data: CharacterConditionUpdate,
        current_user: UserResponse,
    ) -> CharacterConditionResponse:
        """Change a condition's exhaustion_level or source."""

        await self.get_character_for_user(character_id, current_user)

        row = await self._get_condition_or_404(character_id, condition)

        update_data = data.model_dump(exclude_unset=True)
        merged_level = update_data.get("exhaustion_level", row.exhaustion_level)
        self._validate_exhaustion_level(condition, merged_level)

        updated_row = await self.condition_repository.update_character_condition(row, update_data)
        return CharacterConditionResponse.model_validate(updated_row)

    async def remove_condition(self, character_id: int, condition: ConditionType, current_user: UserResponse) -> bool:
        """Remove an active condition from a character."""

        await self.get_character_for_user(character_id, current_user)

        row = await self._get_condition_or_404(character_id, condition)
        return await self.condition_repository.remove_character_condition(row)

    async def _get_condition_or_404(self, character_id: int, condition: ConditionType) -> CharacterCondition:
        """Fetch a condition scoped to the character, or raise ``CharacterConditionNotFoundException``."""

        row = await self.condition_repository.get_character_condition(character_id, condition)
        if not row:
            raise CharacterConditionNotFoundException(character_id=character_id, condition=condition)

        return row

    @staticmethod
    def _validate_exhaustion_level(condition: ConditionType, exhaustion_level: int | None) -> None:
        """Raise ``InvalidConditionException`` unless ``exhaustion_level`` follows the EXHAUSTION rules."""

        if condition == ConditionType.EXHAUSTION and exhaustion_level is None:
            raise InvalidConditionException("exhaustion_level is required when condition is EXHAUSTION (1-6).")

        if condition != ConditionType.EXHAUSTION and exhaustion_level is not None:
            raise InvalidConditionException("exhaustion_level is only valid when condition is EXHAUSTION.")
