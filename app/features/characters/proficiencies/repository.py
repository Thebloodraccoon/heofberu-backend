"""
Character proficiency repository: read-only queries across the four
materialized proficiency tables (skills, saving throws, armor, weapons),
each with its granting ``CharacterFeature`` (and that feature's reference
``Feature``) eager-loaded for provenance.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, selectinload

from app.models.character.armor_proficiency import CharacterArmorProficiency
from app.models.character.character_feature_model import CharacterFeature
from app.models.character.saving_throw_proficiency import CharacterSavingThrowProficiency
from app.models.character.skill_proficiency import CharacterSkillProficiency
from app.models.character.weapon_proficiency import CharacterWeaponProficiency


def _source_grant_load(source_grant_attr: InstrumentedAttribute):
    """Eager-load a proficiency row's ``source_grant`` plus its ``Feature``."""

    return selectinload(source_grant_attr).selectinload(CharacterFeature.feature)


class CharacterProficiencyRepository:
    """Read-only queries for a character's materialized proficiency rows."""

    def __init__(self, db: AsyncSession):
        """Create the repository over the shared session."""

        self.db = db

    async def get_skills(self, character_id: int) -> list[CharacterSkillProficiency]:
        """List the character's skill proficiencies, each with its source grant eager-loaded."""

        result = await self.db.execute(
            select(CharacterSkillProficiency)
            .options(_source_grant_load(CharacterSkillProficiency.source_grant))
            .where(CharacterSkillProficiency.character_id == character_id)
        )
        return list(result.scalars().unique().all())

    async def get_saving_throws(self, character_id: int) -> list[CharacterSavingThrowProficiency]:
        """List the character's saving-throw proficiencies, each with its source grant eager-loaded."""

        result = await self.db.execute(
            select(CharacterSavingThrowProficiency)
            .options(_source_grant_load(CharacterSavingThrowProficiency.source_grant))
            .where(CharacterSavingThrowProficiency.character_id == character_id)
        )
        return list(result.scalars().unique().all())

    async def get_armor(self, character_id: int) -> list[CharacterArmorProficiency]:
        """List the character's armor proficiencies, each with its source grant eager-loaded."""

        result = await self.db.execute(
            select(CharacterArmorProficiency)
            .options(_source_grant_load(CharacterArmorProficiency.source_grant))
            .where(CharacterArmorProficiency.character_id == character_id)
        )
        return list(result.scalars().unique().all())

    async def get_weapons(self, character_id: int) -> list[CharacterWeaponProficiency]:
        """List the character's weapon proficiencies, each with its source grant eager-loaded."""

        result = await self.db.execute(
            select(CharacterWeaponProficiency)
            .options(_source_grant_load(CharacterWeaponProficiency.source_grant))
            .where(CharacterWeaponProficiency.character_id == character_id)
        )
        return list(result.scalars().unique().all())
