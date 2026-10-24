"""Read queries of the public character card (column rows, never the full sheet)."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.core.base.repository import SessionRepository
from app.models.character.character_ability_score_model import CharacterAbilityScore
from app.models.character.character_backstory_model import CharacterBackstory
from app.models.character.character_model import Character
from app.models.user_model import User


def summary_columns() -> list[Any]:
    """Columns of ``PublicCharacterSummary`` (needs ``with_summary_joins``)."""

    return [
        Character.id,
        Character.name,
        Character.level,
        Character.class_id,
        Character.subclass_id,
        Character.race_id,
        Character.subrace_id,
        Character.background_id,
        User.username.label("owner_username"),
        Character.public_visibility,
    ]


def with_summary_joins(stmt: Any) -> Any:
    """Join the owner's username ``summary_columns`` read (race/class names are the client's lookup by id)."""

    return stmt.join(User, User.id == Character.owner_id)


class CharacterVisibilityRepository(SessionRepository):
    """The owner's visibility switch and the public card reads."""

    async def get_owner_and_visibility(self, character_id: int) -> Any:
        """``(owner_id, public_visibility)`` of the character, or ``None`` when it doesn't exist."""

        result = await self.db.execute(
            select(Character.owner_id, Character.public_visibility).where(Character.id == character_id)
        )
        return result.first()

    async def set_visibility(self, character_id: int, visibility: Any) -> None:
        """Write the new visibility (flush only)."""

        character = await self.db.get(Character, character_id)
        character.public_visibility = visibility
        await self.flush()

    async def get_card_row(self, character_id: int) -> Any:
        """Summary columns plus the personality fields, backstory, base ability scores and totals, in one row."""

        backstory = aliased(CharacterBackstory)
        stmt = with_summary_joins(
            select(
                *summary_columns(),
                Character.personality_traits,
                Character.ideals,
                Character.bonds,
                Character.flaws,
                backstory.content.label("backstory"),
                Character.strength,
                Character.dexterity,
                Character.constitution,
                Character.intelligence,
                Character.wisdom,
                Character.charisma,
                CharacterAbilityScore.strength_total,
                CharacterAbilityScore.dexterity_total,
                CharacterAbilityScore.constitution_total,
                CharacterAbilityScore.intelligence_total,
                CharacterAbilityScore.wisdom_total,
                CharacterAbilityScore.charisma_total,
            )
        )
        stmt = (
            stmt.outerjoin(backstory, backstory.character_id == Character.id)
            .outerjoin(CharacterAbilityScore, CharacterAbilityScore.character_id == Character.id)
            .where(Character.id == character_id)
        )
        return (await self.db.execute(stmt)).first()
