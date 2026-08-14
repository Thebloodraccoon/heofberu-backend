"""Per-feature dependency providers for the characters domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.characters.attacks.service import CharacterAttackService
from app.features.characters.conditions.service import CharacterConditionService
from app.features.characters.core.service import CharacterService
from app.features.characters.feats.service import CharacterFeatService
from app.features.characters.features.service import CharacterFeatureService
from app.features.characters.items.service import CharacterItemService
from app.features.characters.proficiencies.service import CharacterProficiencyService
from app.features.characters.progression.service import CharacterProgressionService
from app.features.characters.spells.service import CharacterSpellService


def get_character_service(db: DatabaseDep) -> CharacterService:
    """Get the character service instance."""

    return CharacterService(db)


CharacterServiceDep = Annotated[CharacterService, Depends(get_character_service)]


def get_character_proficiency_service(db: DatabaseDep) -> CharacterProficiencyService:
    """Get the character proficiency service instance."""

    return CharacterProficiencyService(db)


CharacterProficiencyServiceDep = Annotated[CharacterProficiencyService, Depends(get_character_proficiency_service)]


def get_character_spell_service(db: DatabaseDep) -> CharacterSpellService:
    """Get the character spell service instance."""

    return CharacterSpellService(db)


CharacterSpellServiceDep = Annotated[CharacterSpellService, Depends(get_character_spell_service)]


def get_character_attack_service(db: DatabaseDep) -> CharacterAttackService:
    """Get the character attack service instance."""

    return CharacterAttackService(db)


CharacterAttackServiceDep = Annotated[CharacterAttackService, Depends(get_character_attack_service)]


def get_character_feat_service(db: DatabaseDep) -> CharacterFeatService:
    """Get the character feat service instance."""

    return CharacterFeatService(db)


CharacterFeatServiceDep = Annotated[CharacterFeatService, Depends(get_character_feat_service)]


def get_character_feature_service(db: DatabaseDep) -> CharacterFeatureService:
    """Get the character feature service instance."""

    return CharacterFeatureService(db)


CharacterFeatureServiceDep = Annotated[CharacterFeatureService, Depends(get_character_feature_service)]


def get_character_item_service(db: DatabaseDep) -> CharacterItemService:
    """Get the character item service instance."""

    return CharacterItemService(db)


CharacterItemServiceDep = Annotated[CharacterItemService, Depends(get_character_item_service)]


def get_character_condition_service(db: DatabaseDep) -> CharacterConditionService:
    """Get the character condition service instance."""

    return CharacterConditionService(db)


CharacterConditionServiceDep = Annotated[CharacterConditionService, Depends(get_character_condition_service)]


def get_character_progression_service(db: DatabaseDep) -> CharacterProgressionService:
    """Get the character progression service instance."""

    return CharacterProgressionService(db)


CharacterProgressionServiceDep = Annotated[CharacterProgressionService, Depends(get_character_progression_service)]
