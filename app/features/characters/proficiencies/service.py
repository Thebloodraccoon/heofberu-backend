"""Character proficiency service: full-replace of skills and saving throws."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.service import BaseService
from app.features.characters.base import CharacterSubDomainService
from app.features.characters.cache import invalidate_character_cache
from app.features.characters.proficiencies.exceptions import (
    SkillNotAvailableForClassException,
    TooManySkillChoicesException,
)
from app.features.characters.proficiencies.repository import CharacterProficiencyRepository
from app.features.characters.proficiencies.schemas import (
    SavingThrowProficienciesUpdate,
    SkillProficienciesUpdate,
)
from app.features.characters.schemas import CharacterResponse
from app.features.classes.crud.repository import ClassRepository
from app.features.skills.crud.repository import SkillRepository
from app.features.users.schemas import UserResponse


class CharacterProficiencyService(CharacterSubDomainService):
    """
    Skill and saving-throw proficiencies for a character.

    Both are full-replacement operations. Access control is enforced
    against the owning character via the inherited
    ``CharacterSubDomainService`` wiring, but the proficiency rows
    themselves are read/written through
    ``CharacterProficiencyRepository`` since they live in their own
    association tables (``character_skill_proficiencies``,
    ``character_saving_throw_proficiencies``), separate from the crud
    character record handled by ``crud.CharacterService``.

    When a character has a class, skill proficiency choices are validated
    against the class's ``available_skills`` (each chosen skill must be
    in that list) and ``skill_choice_count`` (the number of chosen skills
    must not exceed this limit).

    Unlike the other sub-domains, these methods serialize a full
    ``CharacterResponse``, so the shared access-check fetch must eager-
    load the character's collections (``_light_character_fetch = False``).
    """

    _light_character_fetch = False

    def __init__(self, db: AsyncSession):
        super().__init__(db)
        self.proficiency_repository = CharacterProficiencyRepository(db)
        self.skill_repository = SkillRepository(db)
        self.class_repository = ClassRepository(db)

    async def set_skill_proficiencies(
        self, character_id: int, data: SkillProficienciesUpdate, current_user: UserResponse
    ) -> CharacterResponse:
        """
        Fully replace a character's skill proficiencies (with expertise flags).

        Skill IDs are validated through the base layer's ``resolve_ids``
        helper (same path backgrounds/races use for their granted skills):
        any ID that doesn't resolve raises ``RecordIdsInvalidError``, which
        the data-layer handler maps to a 400. The old character-specific
        ``InvalidSkillIdsException`` is gone.

        When the character has a class, each skill must be in the class's
        ``available_skills`` list, and the total count must not exceed
        ``skill_choice_count``.
        """

        character = await self.get_character_for_user(character_id, current_user)

        skill_ids = [item.skill_id for item in data.skill_proficiencies]
        if skill_ids:
            await BaseService.resolve_ids(self.skill_repository.get_skills_by_ids, skill_ids, "Skill")

        if character.class_id is not None:
            character_class = await self.class_repository.get_by_id(character.class_id)
            if character_class is not None:
                self._validate_skill_choices_against_class(
                    skill_ids,
                    character_class.available_skills,
                    character_class.skill_choice_count,
                    character_class.id,
                )

        proficiencies = [
            {"skill_id": item.skill_id, "is_expertise": item.is_expertise} for item in data.skill_proficiencies
        ]
        await self.proficiency_repository.set_skill_proficiencies(character, proficiencies)
        updated_character = await self.get_character_for_user(character_id, current_user)
        await invalidate_character_cache(character_id)

        return CharacterResponse.model_validate(updated_character)

    async def set_saving_throw_proficiencies(
        self, character_id: int, data: SavingThrowProficienciesUpdate, current_user: UserResponse
    ) -> CharacterResponse:
        """Fully replace a character's saving throw proficiencies."""

        character = await self.get_character_for_user(character_id, current_user)

        await self.proficiency_repository.set_saving_throw_proficiencies(
            character, data.saving_throws
        )
        updated_character = await self.get_character_for_user(character_id, current_user)
        await invalidate_character_cache(character_id)

        return CharacterResponse.model_validate(updated_character)

    @staticmethod
    def _validate_skill_choices_against_class(
        skill_ids: list[int],
        available_skills: list,
        skill_choice_count: int,
        class_id: int,
    ) -> None:
        """
        Validate skill choices against class constraints.

        Raises ``SkillNotAvailableForClassException`` if any skill_id is
        not in the class's ``available_skills``, or
        ``TooManySkillChoicesException`` if the count exceeds
        ``skill_choice_count``.
        """

        if available_skills:
            available_ids = {skill.id for skill in available_skills}
            for skill_id in skill_ids:
                if skill_id not in available_ids:
                    raise SkillNotAvailableForClassException(class_id=class_id, skill_id=skill_id)

        if skill_choice_count is not None and len(skill_ids) > skill_choice_count:
            raise TooManySkillChoicesException(
                class_id=class_id, allowed=skill_choice_count, requested=len(skill_ids),
            )
