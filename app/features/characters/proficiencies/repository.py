"""Character proficiency repository: skill and saving-throw full-replace."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.repository import BaseRepository
from app.models.character_association_models import (
    CharacterSavingThrowProficiency,
    CharacterSkillProficiency,
)
from app.models.character_model import Character


class CharacterProficiencyRepository(BaseRepository[CharacterSkillProficiency]):
    """
    Repository for a character's skill and saving-throw proficiencies.

    Split out of ``CharacterRepository`` — these are their own
    association tables (``character_skill_proficiencies``,
    ``character_saving_throw_proficiencies``), unrelated to the
    ``Character`` row's own columns. Bound to ``CharacterSkillProficiency``
    as its primary model since that's the more actively queried of the
    two; ``BaseRepository``'s generic CRUD isn't used directly here since
    both operations are full-replacement, not per-row create/update.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(CharacterSkillProficiency, db)

    async def get_skill_proficiency(self, character_id: int, skill_id: int) -> CharacterSkillProficiency | None:
        """Fetch a single skill proficiency row, or None if not present."""

        result = await self.db.execute(
            select(CharacterSkillProficiency).where(
                CharacterSkillProficiency.character_id == character_id,
                CharacterSkillProficiency.skill_id == skill_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_saving_throw_proficiency(
        self, character_id: int, ability: str
    ) -> CharacterSavingThrowProficiency | None:
        """Fetch a single saving throw proficiency row, or None if not present."""

        result = await self.db.execute(
            select(CharacterSavingThrowProficiency).where(
                CharacterSavingThrowProficiency.character_id == character_id,
                CharacterSavingThrowProficiency.ability == ability,
            )
        )
        return result.scalar_one_or_none()

    async def set_skill_proficiencies(self, character: Character, proficiencies: list[dict]) -> Character:
        """
        Replace all skill proficiencies for a character with the given list.

        Each item is expected to have 'skill_id' and 'is_expertise'.
        """

        await self.db.execute(
            delete(CharacterSkillProficiency).where(CharacterSkillProficiency.character_id == character.id)
        )

        for item in proficiencies:
            self.db.add(
                CharacterSkillProficiency(
                    character_id=character.id,
                    skill_id=item["skill_id"],
                    is_expertise=item.get("is_expertise", False),
                )
            )

        await self.db.commit()
        self.db.expire(character, ["skill_proficiencies"])
        return character

    async def set_saving_throw_proficiencies(self, character: Character, abilities: list[str]) -> Character:
        """Replace all saving throw proficiencies for a character with the given list."""

        await self.db.execute(
            delete(CharacterSavingThrowProficiency).where(CharacterSavingThrowProficiency.character_id == character.id)
        )

        for ability in abilities:
            self.db.add(CharacterSavingThrowProficiency(character_id=character.id, ability=ability))

        await self.db.commit()
        self.db.expire(character, ["saving_throw_proficiencies"])
        return character
