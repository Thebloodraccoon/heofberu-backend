"""
GM proficiency service: direct add/remove/expertise writes on a character's
skill/saving-throw/armor/weapon proficiency rows. Every write is logged to
``character_proficiency_audit_log`` — the materialized proficiency tables
themselves carry no history, so a GM removing a proficiency (or revoking
expertise) would otherwise be silent.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import AbilityScore, ArmorProficiency, ProficiencyAuditAction, ProficiencyType, WeaponProficiency
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.cache import invalidate_character_cache
from app.features.characters.gm_panel.exceptions import (
    ProficiencyAlreadyGrantedException,
    ProficiencyNotFoundException,
    SkillProficiencyNotFoundException,
)
from app.features.characters.gm_panel.proficiencies.repository import (
    CharacterArmorProficiencyRepository,
    CharacterProficiencyAuditRepository,
    CharacterSavingThrowProficiencyRepository,
    CharacterSkillProficiencyRepository,
    CharacterWeaponProficiencyRepository,
)
from app.features.characters.gm_panel.proficiencies.schemas import SkillExpertiseUpdate
from app.features.characters.grants.schemas import (
    CharacterArmorProficiencyResponse,
    CharacterSavingThrowProficiencyResponse,
    CharacterWeaponProficiencyResponse,
)
from app.features.characters.schemas import SkillProficiencyResponse
from app.features.users.schemas import UserResponse


class GmPanelProficiencyService(CharacterSubDomainService):
    """Add/remove/expertise-toggle a character's proficiency rows, GM-only, each write audited."""

    def __init__(self, db: AsyncSession):
        """Wire up the four proficiency repositories and the audit log."""

        super().__init__(db)
        self.skill_repository = CharacterSkillProficiencyRepository(db)
        self.saving_throw_repository = CharacterSavingThrowProficiencyRepository(db)
        self.armor_repository = CharacterArmorProficiencyRepository(db)
        self.weapon_repository = CharacterWeaponProficiencyRepository(db)
        self.audit_repository = CharacterProficiencyAuditRepository(db)

    # --- Skills ---------------------------------------------------------

    async def add_skill(
        self, character_id: int, skill_id: int, current_user: UserResponse
    ) -> SkillProficiencyResponse:
        """Grant a character proficiency in a skill."""

        await self.get_character_for_user(character_id, current_user)

        if await self.skill_repository.get_proficiency(character_id, skill_id) is not None:
            raise ProficiencyAlreadyGrantedException(character_id, f"proficiency in skill {skill_id}")

        row = await self.skill_repository.add_proficiency(character_id, skill_id)
        await self.audit_repository.log(
            character_id, ProficiencyType.SKILL, ProficiencyAuditAction.ADD,
            actor_user_id=current_user.id, skill_id=skill_id,
        )
        await invalidate_character_cache(character_id)
        return SkillProficiencyResponse.model_validate(row)

    async def remove_skill(self, character_id: int, skill_id: int, current_user: UserResponse) -> None:
        """Revoke a character's proficiency in a skill."""

        await self.get_character_for_user(character_id, current_user)

        row = await self.skill_repository.get_proficiency(character_id, skill_id)
        if row is None:
            raise SkillProficiencyNotFoundException(character_id=character_id, skill_id=skill_id)

        await self.skill_repository.remove_proficiency(row)
        await self.audit_repository.log(
            character_id, ProficiencyType.SKILL, ProficiencyAuditAction.REMOVE,
            actor_user_id=current_user.id, skill_id=skill_id,
        )
        await invalidate_character_cache(character_id)

    async def set_skill_expertise(
        self, character_id: int, skill_id: int, data: SkillExpertiseUpdate, current_user: UserResponse
    ) -> SkillProficiencyResponse:
        """Set is_expertise on one of the character's skill proficiencies."""

        await self.get_character_for_user(character_id, current_user)

        proficiency = await self.skill_repository.get_proficiency(character_id, skill_id)
        if proficiency is None:
            raise SkillProficiencyNotFoundException(character_id=character_id, skill_id=skill_id)

        updated = await self.skill_repository.set_expertise(proficiency, data.is_expertise)
        await self.audit_repository.log(
            character_id, ProficiencyType.SKILL,
            ProficiencyAuditAction.EXPERTISE_GRANTED if data.is_expertise else ProficiencyAuditAction.EXPERTISE_REVOKED,
            actor_user_id=current_user.id, skill_id=skill_id,
        )
        await invalidate_character_cache(character_id)
        return SkillProficiencyResponse.model_validate(updated)

    # --- Saving throws ---------------------------------------------------

    async def add_saving_throw(
        self, character_id: int, ability: AbilityScore, current_user: UserResponse
    ) -> CharacterSavingThrowProficiencyResponse:
        """Grant a character proficiency in a saving throw."""

        await self.get_character_for_user(character_id, current_user)

        if await self.saving_throw_repository.get_proficiency(character_id, ability) is not None:
            raise ProficiencyAlreadyGrantedException(character_id, f"proficiency in the {ability.value} saving throw")

        row = await self.saving_throw_repository.add_proficiency(character_id, ability)
        await self.audit_repository.log(
            character_id, ProficiencyType.SAVING_THROW, ProficiencyAuditAction.ADD,
            actor_user_id=current_user.id, ability=ability,
        )
        await invalidate_character_cache(character_id)
        return CharacterSavingThrowProficiencyResponse.model_validate(row)

    async def remove_saving_throw(self, character_id: int, ability: AbilityScore, current_user: UserResponse) -> None:
        """Revoke a character's proficiency in a saving throw."""

        await self.get_character_for_user(character_id, current_user)

        row = await self.saving_throw_repository.get_proficiency(character_id, ability)
        if row is None:
            raise ProficiencyNotFoundException(character_id, f"proficiency in the {ability.value} saving throw")

        await self.saving_throw_repository.remove_proficiency(row)
        await self.audit_repository.log(
            character_id, ProficiencyType.SAVING_THROW, ProficiencyAuditAction.REMOVE,
            actor_user_id=current_user.id, ability=ability,
        )
        await invalidate_character_cache(character_id)

    # --- Armor ------------------------------------------------------------

    async def add_armor(
        self, character_id: int, armor_type: ArmorProficiency, current_user: UserResponse
    ) -> CharacterArmorProficiencyResponse:
        """Grant a character proficiency in an armor category."""

        await self.get_character_for_user(character_id, current_user)

        if await self.armor_repository.get_proficiency(character_id, armor_type) is not None:
            raise ProficiencyAlreadyGrantedException(character_id, f"proficiency in {armor_type.value} armor")

        row = await self.armor_repository.add_proficiency(character_id, armor_type)
        await self.audit_repository.log(
            character_id, ProficiencyType.ARMOR, ProficiencyAuditAction.ADD,
            actor_user_id=current_user.id, armor_type=armor_type,
        )
        await invalidate_character_cache(character_id)
        return CharacterArmorProficiencyResponse.model_validate(row)

    async def remove_armor(self, character_id: int, armor_type: ArmorProficiency, current_user: UserResponse) -> None:
        """Revoke a character's proficiency in an armor category."""

        await self.get_character_for_user(character_id, current_user)

        row = await self.armor_repository.get_proficiency(character_id, armor_type)
        if row is None:
            raise ProficiencyNotFoundException(character_id, f"proficiency in {armor_type.value} armor")

        await self.armor_repository.remove_proficiency(row)
        await self.audit_repository.log(
            character_id, ProficiencyType.ARMOR, ProficiencyAuditAction.REMOVE,
            actor_user_id=current_user.id, armor_type=armor_type,
        )
        await invalidate_character_cache(character_id)

    # --- Weapons ------------------------------------------------------------

    async def add_weapon(
        self,
        character_id: int,
        current_user: UserResponse,
        *,
        weapon_category: WeaponProficiency | None,
        item_id: int | None,
    ) -> CharacterWeaponProficiencyResponse:
        """Grant a character proficiency in a weapon category or a single item."""

        await self.get_character_for_user(character_id, current_user)

        existing = (
            await self.weapon_repository.get_by_category(character_id, weapon_category)
            if weapon_category is not None
            else await self.weapon_repository.get_by_item(character_id, item_id)
        )
        if existing is not None:
            detail = f"proficiency in {weapon_category.value} weapons" if weapon_category else f"proficiency in item {item_id}"
            raise ProficiencyAlreadyGrantedException(character_id, detail)

        row = await self.weapon_repository.add_proficiency(
            character_id, weapon_category=weapon_category, item_id=item_id
        )
        await self.audit_repository.log(
            character_id, ProficiencyType.WEAPON, ProficiencyAuditAction.ADD,
            actor_user_id=current_user.id, weapon_category=weapon_category, item_id=item_id,
        )
        await invalidate_character_cache(character_id)
        return CharacterWeaponProficiencyResponse.model_validate(row)

    async def remove_weapon(
        self,
        character_id: int,
        current_user: UserResponse,
        *,
        weapon_category: WeaponProficiency | None,
        item_id: int | None,
    ) -> None:
        """Revoke a character's proficiency in a weapon category or a single item."""

        await self.get_character_for_user(character_id, current_user)

        row = (
            await self.weapon_repository.get_by_category(character_id, weapon_category)
            if weapon_category is not None
            else await self.weapon_repository.get_by_item(character_id, item_id)
        )
        if row is None:
            detail = f"proficiency in {weapon_category.value} weapons" if weapon_category else f"proficiency in item {item_id}"
            raise ProficiencyNotFoundException(character_id, detail)

        await self.weapon_repository.remove_proficiency(row)
        await self.audit_repository.log(
            character_id, ProficiencyType.WEAPON, ProficiencyAuditAction.REMOVE,
            actor_user_id=current_user.id, weapon_category=weapon_category, item_id=item_id,
        )
        await invalidate_character_cache(character_id)
