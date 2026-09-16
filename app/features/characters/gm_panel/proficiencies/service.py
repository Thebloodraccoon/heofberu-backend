"""
GM proficiency service: add/remove/expertise writes on a character's GM
proficiency layer.

Every write here only ever touches the ``source_type=GM`` row for the
target (character, proficiency) — see ``CharacterProficiencyGmRepository``
for the upsert-and-clear rule and ``CharacterProficiency`` for how a GM row
resolves against class/race/background/feature rows. A GM "remove" on a
proficiency the character only has through another source writes a
``REVOKE`` row (a durable veto that survives re-sync); on a proficiency the
character has ONLY because a GM granted it, it clears that grant back to
nothing.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import AbilityScore, ArmorProficiency, ProficiencyAction, ProficiencyType, WeaponProficiency
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.cache import invalidate_character_cache
from app.features.characters.gm_panel.exceptions import (
    ProficiencyAlreadyGrantedException,
    ProficiencyNotFoundException,
    SkillProficiencyNotFoundException,
)
from app.features.characters.gm_panel.proficiencies.repository import CharacterProficiencyGmRepository
from app.features.characters.gm_panel.proficiencies.schemas import SkillExpertiseUpdate
from app.features.characters.grants.schemas import (
    CharacterArmorProficiencyResponse,
    CharacterSavingThrowProficiencyResponse,
    CharacterWeaponProficiencyResponse,
)
from app.features.characters.schemas import SkillProficiencyResponse
from app.features.users.schemas import UserResponse


class GmPanelProficiencyService(CharacterSubDomainService):
    """Add/remove/expertise-toggle a character's GM-layer proficiency rows, GM-only."""

    def __init__(self, db: AsyncSession):
        """Wire up the unified GM proficiency repository."""

        super().__init__(db)
        self.proficiency_repository = CharacterProficiencyGmRepository(db)

    # --- Skills ---------------------------------------------------------

    async def add_skill(
        self, character_id: int, skill_id: int, current_user: UserResponse
    ) -> SkillProficiencyResponse:
        """Grant a character proficiency in a skill."""

        await self.get_character_for_user(character_id, current_user)

        if await self.proficiency_repository.resolve(character_id, ProficiencyType.SKILL, skill_id=skill_id) is not None:
            raise ProficiencyAlreadyGrantedException(character_id, f"proficiency in skill {skill_id}")

        await self.proficiency_repository.set_override(
            character_id,
            ProficiencyType.SKILL,
            ProficiencyAction.GRANT,
            current_user.id,
            skill_id=skill_id,
            is_expertise=False,
        )
        await invalidate_character_cache(character_id)

        row = await self.proficiency_repository.resolve(character_id, ProficiencyType.SKILL, skill_id=skill_id)
        return SkillProficiencyResponse.model_validate(row)

    async def remove_skill(self, character_id: int, skill_id: int, current_user: UserResponse) -> None:
        """Revoke a character's proficiency in a skill."""

        await self.get_character_for_user(character_id, current_user)

        if await self.proficiency_repository.resolve(character_id, ProficiencyType.SKILL, skill_id=skill_id) is None:
            raise SkillProficiencyNotFoundException(character_id=character_id, skill_id=skill_id)

        await self.proficiency_repository.set_override(
            character_id, ProficiencyType.SKILL, ProficiencyAction.REVOKE, current_user.id, skill_id=skill_id
        )
        await invalidate_character_cache(character_id)

    async def set_skill_expertise(
        self, character_id: int, skill_id: int, data: SkillExpertiseUpdate, current_user: UserResponse
    ) -> SkillProficiencyResponse:
        """Set is_expertise on a character's skill proficiency."""

        await self.get_character_for_user(character_id, current_user)

        if await self.proficiency_repository.resolve(character_id, ProficiencyType.SKILL, skill_id=skill_id) is None:
            raise SkillProficiencyNotFoundException(character_id=character_id, skill_id=skill_id)

        await self.proficiency_repository.set_override(
            character_id,
            ProficiencyType.SKILL,
            ProficiencyAction.GRANT,
            current_user.id,
            skill_id=skill_id,
            is_expertise=data.is_expertise,
        )
        await invalidate_character_cache(character_id)

        row = await self.proficiency_repository.resolve(character_id, ProficiencyType.SKILL, skill_id=skill_id)
        return SkillProficiencyResponse.model_validate(row)

    # --- Saving throws ---------------------------------------------------

    async def add_saving_throw(
        self, character_id: int, ability: AbilityScore, current_user: UserResponse
    ) -> CharacterSavingThrowProficiencyResponse:
        """Grant a character proficiency in a saving throw."""

        await self.get_character_for_user(character_id, current_user)

        if await self.proficiency_repository.resolve(character_id, ProficiencyType.SAVING_THROW, ability=ability) is not None:
            raise ProficiencyAlreadyGrantedException(character_id, f"proficiency in the {ability.value} saving throw")

        await self.proficiency_repository.set_override(
            character_id, ProficiencyType.SAVING_THROW, ProficiencyAction.GRANT, current_user.id, ability=ability
        )
        await invalidate_character_cache(character_id)

        row = await self.proficiency_repository.resolve(character_id, ProficiencyType.SAVING_THROW, ability=ability)
        return CharacterSavingThrowProficiencyResponse.model_validate(row)

    async def remove_saving_throw(self, character_id: int, ability: AbilityScore, current_user: UserResponse) -> None:
        """Revoke a character's proficiency in a saving throw."""

        await self.get_character_for_user(character_id, current_user)

        if await self.proficiency_repository.resolve(character_id, ProficiencyType.SAVING_THROW, ability=ability) is None:
            raise ProficiencyNotFoundException(character_id, f"proficiency in the {ability.value} saving throw")

        await self.proficiency_repository.set_override(
            character_id, ProficiencyType.SAVING_THROW, ProficiencyAction.REVOKE, current_user.id, ability=ability
        )
        await invalidate_character_cache(character_id)

    # --- Armor ------------------------------------------------------------

    async def add_armor(
        self, character_id: int, armor_type: ArmorProficiency, current_user: UserResponse
    ) -> CharacterArmorProficiencyResponse:
        """Grant a character proficiency in an armor category."""

        await self.get_character_for_user(character_id, current_user)

        if await self.proficiency_repository.resolve(character_id, ProficiencyType.ARMOR, armor_type=armor_type) is not None:
            raise ProficiencyAlreadyGrantedException(character_id, f"proficiency in {armor_type.value} armor")

        await self.proficiency_repository.set_override(
            character_id, ProficiencyType.ARMOR, ProficiencyAction.GRANT, current_user.id, armor_type=armor_type
        )
        await invalidate_character_cache(character_id)

        row = await self.proficiency_repository.resolve(character_id, ProficiencyType.ARMOR, armor_type=armor_type)
        return CharacterArmorProficiencyResponse.model_validate(row)

    async def remove_armor(self, character_id: int, armor_type: ArmorProficiency, current_user: UserResponse) -> None:
        """Revoke a character's proficiency in an armor category."""

        await self.get_character_for_user(character_id, current_user)

        if await self.proficiency_repository.resolve(character_id, ProficiencyType.ARMOR, armor_type=armor_type) is None:
            raise ProficiencyNotFoundException(character_id, f"proficiency in {armor_type.value} armor")

        await self.proficiency_repository.set_override(
            character_id, ProficiencyType.ARMOR, ProficiencyAction.REVOKE, current_user.id, armor_type=armor_type
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

        discriminator = {"weapon_category": weapon_category, "item_id": item_id}
        if await self.proficiency_repository.resolve(character_id, ProficiencyType.WEAPON, **discriminator) is not None:
            detail = f"proficiency in {weapon_category.value} weapons" if weapon_category else f"proficiency in item {item_id}"
            raise ProficiencyAlreadyGrantedException(character_id, detail)

        await self.proficiency_repository.set_override(
            character_id, ProficiencyType.WEAPON, ProficiencyAction.GRANT, current_user.id, **discriminator
        )
        await invalidate_character_cache(character_id)

        row = await self.proficiency_repository.resolve(character_id, ProficiencyType.WEAPON, **discriminator)
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

        discriminator = {"weapon_category": weapon_category, "item_id": item_id}
        if await self.proficiency_repository.resolve(character_id, ProficiencyType.WEAPON, **discriminator) is None:
            detail = f"proficiency in {weapon_category.value} weapons" if weapon_category else f"proficiency in item {item_id}"
            raise ProficiencyNotFoundException(character_id, detail)

        await self.proficiency_repository.set_override(
            character_id, ProficiencyType.WEAPON, ProficiencyAction.REVOKE, current_user.id, **discriminator
        )
        await invalidate_character_cache(character_id)
