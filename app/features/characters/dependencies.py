"""Per-feature dependency providers for the characters domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.characters.attacks.service import CharacterAttackService
from app.features.characters.backstory.service import CharacterBackstoryService
from app.features.characters.conditions.service import CharacterConditionService
from app.features.characters.crud.service import CharacterService
from app.features.characters.progression.service import CharacterProgressionService
from app.features.characters.spells.service import CharacterSpellService


def get_character_service(db: DatabaseDep) -> CharacterService:
    """Get the character service instance."""

    return CharacterService(db)


CharacterServiceDep = Annotated[CharacterService, Depends(get_character_service)]


def get_character_spell_service(db: DatabaseDep) -> CharacterSpellService:
    """Get the character spell service instance."""

    return CharacterSpellService(db)


CharacterSpellServiceDep = Annotated[CharacterSpellService, Depends(get_character_spell_service)]


def get_character_attack_service(db: DatabaseDep) -> CharacterAttackService:
    """Get the character attack service instance."""

    return CharacterAttackService(db)


CharacterAttackServiceDep = Annotated[CharacterAttackService, Depends(get_character_attack_service)]


def get_character_condition_service(db: DatabaseDep) -> CharacterConditionService:
    """Get the character condition service instance."""

    return CharacterConditionService(db)


CharacterConditionServiceDep = Annotated[CharacterConditionService, Depends(get_character_condition_service)]


def get_character_backstory_service(db: DatabaseDep) -> CharacterBackstoryService:
    """Get the character backstory service instance."""

    return CharacterBackstoryService(db)


CharacterBackstoryServiceDep = Annotated[CharacterBackstoryService, Depends(get_character_backstory_service)]


def get_character_progression_service(db: DatabaseDep) -> CharacterProgressionService:
    """Get the character progression service instance."""

    return CharacterProgressionService(db)


CharacterProgressionServiceDep = Annotated[CharacterProgressionService, Depends(get_character_progression_service)]
