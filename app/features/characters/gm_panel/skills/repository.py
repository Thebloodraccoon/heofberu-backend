"""Repository for a character's skill proficiency rows."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character_association_models import CharacterSkillProficiency


class CharacterSkillProficiencyRepository:
    """Owns character_skill_proficiencies rows (composite PK; generic BaseRepository CRUD does not apply)."""

    def __init__(self, db: AsyncSession):
        """Hold the session backing proficiency rows."""

        self.db = db

    async def get_proficiency(self, character_id: int, skill_id: int) -> CharacterSkillProficiency | None:
        """Fetch a character's proficiency row for a skill, or None."""

        result = await self.db.execute(
            select(CharacterSkillProficiency).where(
                CharacterSkillProficiency.character_id == character_id,
                CharacterSkillProficiency.skill_id == skill_id,
            )
        )
        return result.scalar_one_or_none()

    async def set_expertise(
        self, proficiency: CharacterSkillProficiency, is_expertise: bool, *, commit: bool = True
    ) -> CharacterSkillProficiency:
        """Set is_expertise on a proficiency row and persist it."""

        proficiency.is_expertise = is_expertise

        if commit:
            await self.db.commit()
            await self.db.refresh(proficiency)
        else:
            await self.db.flush()

        return proficiency
