"""Character proficiency service: the read-only proficiency surface, each resolved with every source that grants it."""

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ProficiencyAction, ProficiencySourceType, ProficiencyType
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.grants.effects import load_character_grant_effects
from app.features.characters.proficiencies.repository import CharacterProficiencyRepository
from app.features.characters.proficiencies.schemas import (
    ArmorProficiencyView,
    CharacterProficienciesResponse,
    ProficiencySource,
    SavingThrowProficiencyView,
    SkillProficiencyView,
    WeaponProficiencyView,
)
from app.features.users.schemas import UserResponse
from app.models.character.character_proficiency_model import CharacterProficiency


@dataclass(frozen=True)
class _Entry:
    """One source's claim on a proficiency: a stored row or a feature grant's computed effect."""

    key: tuple
    source: ProficiencySource
    is_expertise: bool = False
    revoke: bool = False


def _group_key(row: CharacterProficiency) -> tuple:
    """The (proficiency_type, *discriminator) key every row of the same proficiency shares."""

    proficiency_type = ProficiencyType(row.proficiency_type)

    if proficiency_type == ProficiencyType.SKILL:
        return (proficiency_type, row.skill_id)
    if proficiency_type == ProficiencyType.SAVING_THROW:
        return (proficiency_type, row.ability)
    if proficiency_type == ProficiencyType.ARMOR:
        return (proficiency_type, row.armor_type)

    return (proficiency_type, row.weapon_category, row.item_id)


def _row_entry(row: CharacterProficiency) -> _Entry:
    """A stored row (class/race/background choice or GM override)."""

    return _Entry(
        key=_group_key(row),
        source=ProficiencySource(source_type=row.source_type, actor_user_id=row.actor_user_id),
        is_expertise=bool(row.is_expertise),
        revoke=row.source_type == ProficiencySourceType.GM and row.action == ProficiencyAction.REVOKE,
    )


class CharacterProficiencyService(CharacterSubDomainService):
    """
    Read-only proficiency surface for a character: skills, saving throws,
    armor, and weapons — each resolved across every contributing source
    (class/race/background choice and GM override rows from
    ``character_proficiencies``, plus feature/feat grants computed from
    their effect tree and the player's picks) into one entry with the full
    list of sources that grant it.

    A GM ``REVOKE`` row excludes the proficiency entirely, regardless of
    how many other sources would otherwise grant it — see
    ``CharacterProficiency`` for the full resolution algorithm.
    """

    def __init__(self, db: AsyncSession):
        """Create the proficiency repository alongside the shared character access check."""

        super().__init__(db)
        self.proficiency_repository = CharacterProficiencyRepository(db)

    async def _grant_entries(self, character_id: int) -> list[_Entry]:
        """Every feature/feat grant's computed proficiencies, tagged with the granting feature."""

        entries = []
        for feature, effects in await load_character_grant_effects(self.repository.db, character_id):
            source = ProficiencySource(
                source_type=ProficiencySourceType.FEATURE,
                feature_id=feature.id,
                feature_name=feature.name,
                feature_source_type=feature.source_type,
            )
            entries += [
                _Entry((ProficiencyType.SKILL, skill_id), source, is_expertise=expertise)
                for skill_id, expertise in effects.skills.items()
            ]
            entries += [_Entry((ProficiencyType.SAVING_THROW, ability), source) for ability in effects.saving_throws]
            entries += [_Entry((ProficiencyType.ARMOR, armor_type), source) for armor_type in effects.armor]
            entries += [_Entry((ProficiencyType.WEAPON, *weapon), source) for weapon in effects.weapons]
        return entries

    async def get_proficiencies(self, character_id: int, current_user: UserResponse) -> CharacterProficienciesResponse:
        """Resolve every proficiency the character currently has, each with its full list of sources."""

        character = await self.get_character_for_user(character_id, current_user)
        rows = await self.proficiency_repository.get_all(character.id)

        grouped: dict[tuple, list[_Entry]] = defaultdict(list)
        for entry in [*map(_row_entry, rows), *await self._grant_entries(character.id)]:
            grouped[entry.key].append(entry)

        response = CharacterProficienciesResponse()

        for (proficiency_type, *discriminator), group in grouped.items():
            if any(entry.revoke for entry in group):
                continue

            sources = [entry.source for entry in group]

            if proficiency_type == ProficiencyType.SKILL:
                response.skills.append(
                    SkillProficiencyView(
                        skill_id=discriminator[0],
                        is_expertise=any(entry.is_expertise for entry in group),
                        sources=sources,
                    )
                )
            elif proficiency_type == ProficiencyType.SAVING_THROW:
                response.saving_throws.append(SavingThrowProficiencyView(ability=discriminator[0], sources=sources))
            elif proficiency_type == ProficiencyType.ARMOR:
                response.armor.append(ArmorProficiencyView(armor_type=discriminator[0], sources=sources))
            else:
                weapon_category, item_id = discriminator
                response.weapons.append(
                    WeaponProficiencyView(weapon_category=weapon_category, item_id=item_id, sources=sources)
                )

        return response
