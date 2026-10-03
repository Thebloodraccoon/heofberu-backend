"""
GM proficiency service: add/remove/expertise writes on a character's GM
proficiency layer.

Every write only ever touches the ``source_type=GM`` row for the target
(character, proficiency) — see ``CharacterProficiencyGmRepository.apply``
for how that row is created, flipped or cleared, and
``app.features.characters.proficiencies.resolver`` for how it resolves
against class/race/background rows and feature/feat grants. A GM "remove"
on a proficiency another source still grants writes a ``REVOKE`` row (a
durable veto); on one only the GM granted it clears the grant back to
nothing. A GM "add" over a ``REVOKE`` clears the veto (or, if nothing else
grants the proficiency any more, replaces it with a ``GRANT``).

Each operation loads the proficiency's rows and feature grants once,
decides, writes in one transaction and builds the response from the
in-memory result.
"""

from functools import partial
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import AbilityScore, ArmorProficiency, ProficiencyType, WeaponProficiency
from app.core.base.transaction import unit_of_work
from app.core.exceptions import RecordNotFoundError
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.cache import invalidate_character_cache
from app.features.characters.gm_panel.exceptions import (
    ProficiencyAlreadyGrantedException,
    ProficiencyNotFoundException,
    SkillProficiencyNotFoundException,
)
from app.features.characters.gm_panel.proficiencies.repository import CharacterProficiencyGmRepository
from app.features.characters.gm_panel.proficiencies.schemas import SkillExpertiseUpdate, SkillProficiencyResponse
from app.features.characters.grants.schemas import (
    CharacterArmorProficiencyResponse,
    CharacterSavingThrowProficiencyResponse,
    CharacterWeaponProficiencyResponse,
)
from app.features.characters.proficiencies.resolver import (
    ProficiencyEntry,
    ResolvedProficiency,
    proficiency_key,
    resolve_group,
    row_entry,
)
from app.features.items.crud.repository import ItemRepository
from app.features.items.exceptions import ItemNotFoundException
from app.features.skills.crud.repository import SkillRepository
from app.features.users.schemas import UserResponse
from app.models.character.character_proficiency_model import CharacterProficiency


class GmPanelProficiencyService(CharacterSubDomainService):
    """Add/remove/expertise-toggle a character's GM-layer proficiency rows, GM-only."""

    def __init__(self, db: AsyncSession):
        """Wire up the unified GM proficiency repository and the reference lookups."""

        super().__init__(db)
        self.proficiency_repository = CharacterProficiencyGmRepository(db)
        self.skill_repository = SkillRepository(db)
        self.item_repository = ItemRepository(db)

    async def add_skill(self, character_id: int, skill_id: int, current_user: UserResponse) -> SkillProficiencyResponse:
        """Grant a character proficiency in a skill."""

        await self.get_character_for_user(character_id, current_user)
        if not await self.skill_repository.exists_by_id(skill_id):
            raise RecordNotFoundError("Skill", str(skill_id))

        resolved = await self._grant(
            character_id,
            current_user,
            ProficiencyType.SKILL,
            f"proficiency in skill {skill_id}",
            skill_id=skill_id,
        )
        return SkillProficiencyResponse(skill_id=skill_id, is_expertise=resolved.is_expertise)

    async def remove_skill(self, character_id: int, skill_id: int, current_user: UserResponse) -> None:
        """Revoke a character's proficiency in a skill."""

        await self.get_character_for_user(character_id, current_user)
        await self._revoke(
            character_id,
            current_user,
            ProficiencyType.SKILL,
            SkillProficiencyNotFoundException(character_id=character_id, skill_id=skill_id),
            skill_id=skill_id,
        )

    async def set_skill_expertise(
        self, character_id: int, skill_id: int, data: SkillExpertiseUpdate, current_user: UserResponse
    ) -> SkillProficiencyResponse:
        """
        Set ``is_expertise`` on a character's skill proficiency. The GM's
        value decides on its own, so it can also clear expertise another
        source (class, feature) gives.
        """

        await self.get_character_for_user(character_id, current_user)

        not_found = SkillProficiencyNotFoundException(character_id=character_id, skill_id=skill_id)
        resolved = await self._write(
            character_id,
            current_user,
            ProficiencyType.SKILL,
            wanted=True,
            is_expertise=data.is_expertise,
            missing=not_found,
            skill_id=skill_id,
        )
        # wanted=True: the skill stays granted, so it always resolves
        return SkillProficiencyResponse(
            skill_id=skill_id, is_expertise=cast(ResolvedProficiency, resolved).is_expertise
        )

    async def add_saving_throw(
        self, character_id: int, ability: AbilityScore, current_user: UserResponse
    ) -> CharacterSavingThrowProficiencyResponse:
        """Grant a character proficiency in a saving throw."""

        await self.get_character_for_user(character_id, current_user)
        await self._grant(
            character_id,
            current_user,
            ProficiencyType.SAVING_THROW,
            f"proficiency in the {ability.value} saving throw",
            ability=ability,
        )
        return CharacterSavingThrowProficiencyResponse(ability=ability)

    async def remove_saving_throw(self, character_id: int, ability: AbilityScore, current_user: UserResponse) -> None:
        """Revoke a character's proficiency in a saving throw."""

        await self.get_character_for_user(character_id, current_user)
        await self._revoke(
            character_id,
            current_user,
            ProficiencyType.SAVING_THROW,
            ProficiencyNotFoundException(character_id, f"proficiency in the {ability.value} saving throw"),
            ability=ability,
        )

    async def add_armor(
        self, character_id: int, armor_type: ArmorProficiency, current_user: UserResponse
    ) -> CharacterArmorProficiencyResponse:
        """Grant a character proficiency in an armor category."""

        await self.get_character_for_user(character_id, current_user)
        await self._grant(
            character_id,
            current_user,
            ProficiencyType.ARMOR,
            f"proficiency in {armor_type.value} armor",
            armor_type=armor_type,
        )
        return CharacterArmorProficiencyResponse(armor_type=armor_type)

    async def remove_armor(self, character_id: int, armor_type: ArmorProficiency, current_user: UserResponse) -> None:
        """Revoke a character's proficiency in an armor category."""

        await self.get_character_for_user(character_id, current_user)
        await self._revoke(
            character_id,
            current_user,
            ProficiencyType.ARMOR,
            ProficiencyNotFoundException(character_id, f"proficiency in {armor_type.value} armor"),
            armor_type=armor_type,
        )

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
        if item_id is not None and not await self.item_repository.exists_by_id(item_id):
            raise ItemNotFoundException(item_id=item_id)

        await self._grant(
            character_id,
            current_user,
            ProficiencyType.WEAPON,
            self._weapon_detail(weapon_category, item_id),
            weapon_category=weapon_category,
            item_id=item_id,
        )
        return CharacterWeaponProficiencyResponse(weapon_category=weapon_category, item_id=item_id)

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
        await self._revoke(
            character_id,
            current_user,
            ProficiencyType.WEAPON,
            ProficiencyNotFoundException(character_id, self._weapon_detail(weapon_category, item_id)),
            weapon_category=weapon_category,
            item_id=item_id,
        )

    @staticmethod
    def _weapon_detail(weapon_category: WeaponProficiency | None, item_id: int | None) -> str:
        """Human-readable target of a weapon proficiency, for error messages."""

        return (
            f"proficiency in {weapon_category.value} weapons" if weapon_category else f"proficiency in item {item_id}"
        )

    async def _grant(
        self,
        character_id: int,
        current_user: UserResponse,
        proficiency_type: ProficiencyType,
        detail: str,
        **discriminator: Any,
    ) -> ResolvedProficiency:
        """Grant one proficiency; ``409`` if the character already has it from any source."""

        resolved = await self._write(
            character_id,
            current_user,
            proficiency_type,
            wanted=True,
            already=ProficiencyAlreadyGrantedException(character_id, detail),
            **discriminator,
        )
        return cast(ResolvedProficiency, resolved)  # wanted=True always resolves to the new grant

    async def _revoke(
        self,
        character_id: int,
        current_user: UserResponse,
        proficiency_type: ProficiencyType,
        missing: Exception,
        **discriminator: Any,
    ) -> None:
        """Revoke one proficiency; ``404`` (``missing``) if the character does not have it."""

        await self._write(
            character_id,
            current_user,
            proficiency_type,
            wanted=False,
            missing=missing,
            **discriminator,
        )

    async def _write(
        self,
        character_id: int,
        current_user: UserResponse,
        proficiency_type: ProficiencyType,
        *,
        wanted: bool,
        is_expertise: bool | None = None,
        already: Exception | None = None,
        missing: Exception | None = None,
        **discriminator: Any,
    ) -> ResolvedProficiency | None:
        """
        Load the proficiency's rows and feature grants once, validate the
        precondition (``already`` is raised when it is granted, ``missing``
        when it is not), apply the GM-layer change in one transaction and
        return the proficiency as it resolves afterwards.
        """

        rows = await self.proficiency_repository.get_rows(character_id, proficiency_type, **discriminator)
        features = await self.proficiency_repository.feature_entries(character_id, proficiency_type, **discriminator)
        entries = [*map(row_entry, rows), *features]
        key = proficiency_key(proficiency_type, **discriminator)

        granted_now = resolve_group(key, entries) is not None
        if granted_now and already is not None:
            raise already
        if not granted_now and missing is not None:
            raise missing

        async with unit_of_work(self.repository.db) as uow:
            gm_row = await self.proficiency_repository.apply(
                character_id,
                proficiency_type,
                rows,
                granted=wanted,
                others_grant=any(not entry.is_gm for entry in entries),
                actor_user_id=current_user.id,
                is_expertise=is_expertise,
                **discriminator,
            )
            resolved = resolve_group(key, self._after_write(entries, gm_row))
            await uow.after_commit(partial(invalidate_character_cache, character_id))

        return resolved

    @staticmethod
    def _after_write(entries: list[ProficiencyEntry], gm_row: CharacterProficiency | None) -> list[ProficiencyEntry]:
        """The entries as they stand once the GM layer holds ``gm_row`` (``None`` = no GM row)."""

        others = [entry for entry in entries if not entry.is_gm]
        return [*others, row_entry(gm_row)] if gm_row is not None else others
