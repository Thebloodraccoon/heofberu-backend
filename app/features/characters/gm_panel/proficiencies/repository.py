"""
Repositories backing the GM proficiency panel: direct add/remove/expertise
writes on a character's skill/saving-throw/armor/weapon proficiency rows,
plus the append-only audit log of those writes.

None of the four proficiency tables use ``BaseRepository`` — each has its
own natural key (composite PK, or a per-character-per-value uniqueness) and
no generic listing/pagination is needed here (that's ``CharacterProficiencyRepository``
in ``app.features.characters.proficiencies.repository``, the player-facing read side).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import AbilityScore, ArmorProficiency, ProficiencyAuditAction, ProficiencyType, WeaponProficiency
from app.core.base.repository import _commit_or_rollback
from app.models.character_association_models import CharacterSkillProficiency
from app.models.character_engine_models import (
    CharacterArmorProficiency,
    CharacterSavingThrowProficiency,
    CharacterWeaponProficiency,
)
from app.models.character_proficiency_audit_model import CharacterProficiencyAuditLog


class CharacterSkillProficiencyRepository:
    """Owns ``character_skill_proficiencies`` rows (composite PK; generic ``BaseRepository`` CRUD does not apply)."""

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

    async def add_proficiency(self, character_id: int, skill_id: int) -> CharacterSkillProficiency:
        """Add a free-form skill proficiency row (``source_character_feature_id`` stays NULL)."""

        row = CharacterSkillProficiency(character_id=character_id, skill_id=skill_id, is_expertise=False)
        self.db.add(row)
        await _commit_or_rollback(self.db)
        return row

    async def remove_proficiency(self, row: CharacterSkillProficiency) -> None:
        """Delete a skill proficiency row."""

        await self.db.delete(row)
        await _commit_or_rollback(self.db)

    async def set_expertise(self, proficiency: CharacterSkillProficiency, is_expertise: bool) -> CharacterSkillProficiency:
        """Set ``is_expertise`` on a proficiency row and persist it."""

        proficiency.is_expertise = is_expertise
        await _commit_or_rollback(self.db)
        await self.db.refresh(proficiency)
        return proficiency


class CharacterSavingThrowProficiencyRepository:
    """Owns ``character_saving_throw_proficiencies`` rows."""

    def __init__(self, db: AsyncSession):
        """Hold the session backing proficiency rows."""

        self.db = db

    async def get_proficiency(self, character_id: int, ability: AbilityScore) -> CharacterSavingThrowProficiency | None:
        """Fetch a character's saving-throw proficiency row for an ability, or None."""

        result = await self.db.execute(
            select(CharacterSavingThrowProficiency).where(
                CharacterSavingThrowProficiency.character_id == character_id,
                CharacterSavingThrowProficiency.ability == ability,
            )
        )
        return result.scalar_one_or_none()

    async def add_proficiency(self, character_id: int, ability: AbilityScore) -> CharacterSavingThrowProficiency:
        """Add a free-form saving-throw proficiency row."""

        row = CharacterSavingThrowProficiency(character_id=character_id, ability=ability)
        self.db.add(row)
        await _commit_or_rollback(self.db)
        return row

    async def remove_proficiency(self, row: CharacterSavingThrowProficiency) -> None:
        """Delete a saving-throw proficiency row."""

        await self.db.delete(row)
        await _commit_or_rollback(self.db)


class CharacterArmorProficiencyRepository:
    """Owns ``character_armor_proficiencies`` rows."""

    def __init__(self, db: AsyncSession):
        """Hold the session backing proficiency rows."""

        self.db = db

    async def get_proficiency(self, character_id: int, armor_type: ArmorProficiency) -> CharacterArmorProficiency | None:
        """Fetch a character's armor proficiency row for an armor type, or None."""

        result = await self.db.execute(
            select(CharacterArmorProficiency).where(
                CharacterArmorProficiency.character_id == character_id,
                CharacterArmorProficiency.armor_type == armor_type,
            )
        )
        return result.scalar_one_or_none()

    async def add_proficiency(self, character_id: int, armor_type: ArmorProficiency) -> CharacterArmorProficiency:
        """Add a free-form armor proficiency row."""

        row = CharacterArmorProficiency(character_id=character_id, armor_type=armor_type)
        self.db.add(row)
        await _commit_or_rollback(self.db)
        return row

    async def remove_proficiency(self, row: CharacterArmorProficiency) -> None:
        """Delete an armor proficiency row."""

        await self.db.delete(row)
        await _commit_or_rollback(self.db)


class CharacterWeaponProficiencyRepository:
    """Owns ``character_weapon_proficiencies`` rows (category XOR item)."""

    def __init__(self, db: AsyncSession):
        """Hold the session backing proficiency rows."""

        self.db = db

    async def get_by_category(
        self, character_id: int, weapon_category: WeaponProficiency
    ) -> CharacterWeaponProficiency | None:
        """Fetch a character's category weapon proficiency row, or None."""

        result = await self.db.execute(
            select(CharacterWeaponProficiency).where(
                CharacterWeaponProficiency.character_id == character_id,
                CharacterWeaponProficiency.weapon_category == weapon_category,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_item(self, character_id: int, item_id: int) -> CharacterWeaponProficiency | None:
        """Fetch a character's single-item weapon proficiency row, or None."""

        result = await self.db.execute(
            select(CharacterWeaponProficiency).where(
                CharacterWeaponProficiency.character_id == character_id,
                CharacterWeaponProficiency.item_id == item_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_proficiency(
        self, character_id: int, *, weapon_category: WeaponProficiency | None, item_id: int | None
    ) -> CharacterWeaponProficiency:
        """Add a free-form weapon proficiency row — a whole category or a single item."""

        row = CharacterWeaponProficiency(character_id=character_id, weapon_category=weapon_category, item_id=item_id)
        self.db.add(row)
        await _commit_or_rollback(self.db)
        return row

    async def remove_proficiency(self, row: CharacterWeaponProficiency) -> None:
        """Delete a weapon proficiency row."""

        await self.db.delete(row)
        await _commit_or_rollback(self.db)


class CharacterProficiencyAuditRepository:
    """Append-only writer for ``character_proficiency_audit_log``."""

    def __init__(self, db: AsyncSession):
        """Hold the session backing the audit log."""

        self.db = db

    async def log(
        self,
        character_id: int,
        proficiency_type: ProficiencyType,
        action: ProficiencyAuditAction,
        *,
        actor_user_id: int | None,
        skill_id: int | None = None,
        ability: AbilityScore | None = None,
        armor_type: ArmorProficiency | None = None,
        weapon_category: WeaponProficiency | None = None,
        item_id: int | None = None,
        notes: str = "",
    ) -> CharacterProficiencyAuditLog:
        """Append one audit row. Never rolled back by the caller's business validation — write-then-commit."""

        row = CharacterProficiencyAuditLog(
            character_id=character_id,
            proficiency_type=proficiency_type,
            action=action,
            actor_user_id=actor_user_id,
            skill_id=skill_id,
            ability=ability,
            armor_type=armor_type,
            weapon_category=weapon_category,
            item_id=item_id,
            notes=notes,
        )
        self.db.add(row)
        await _commit_or_rollback(self.db)
        return row
