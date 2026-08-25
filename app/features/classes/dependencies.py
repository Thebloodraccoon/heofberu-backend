"""Per-capability dependency providers for the classes domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.classes.armor.service import ClassArmorService
from app.features.classes.crud.service import ClassCrudService
from app.features.classes.features.service import ClassFeatureService
from app.features.classes.items.service import ClassItemsService
from app.features.classes.progression.service import ClassProgressionService
from app.features.classes.skills.service import ClassSkillService
from app.features.classes.throws.service import ClassThrowsService
from app.features.classes.weapons.service import ClassWeaponService


def get_class_crud_service(db: DatabaseDep) -> ClassCrudService:
    """Get the class CRUD service instance."""

    return ClassCrudService(db)


ClassCrudDep = Annotated[ClassCrudService, Depends(get_class_crud_service)]


def get_class_feature_service(db: DatabaseDep) -> ClassFeatureService:
    """Get the class feature service instance."""

    return ClassFeatureService(db)


ClassFeaturesDep = Annotated[ClassFeatureService, Depends(get_class_feature_service)]


def get_class_skill_service(db: DatabaseDep) -> ClassSkillService:
    """Get the class skills service instance."""

    return ClassSkillService(db)


ClassSkillsDep = Annotated[ClassSkillService, Depends(get_class_skill_service)]


def get_class_item_service(db: DatabaseDep) -> ClassItemsService:
    """Get the class starting-items service instance."""

    return ClassItemsService(db)


ClassItemsDep = Annotated[ClassItemsService, Depends(get_class_item_service)]


def get_class_armor_service(db: DatabaseDep) -> ClassArmorService:
    """Get the class armor-proficiencies service instance."""

    return ClassArmorService(db)


ClassArmorDep = Annotated[ClassArmorService, Depends(get_class_armor_service)]


def get_class_weapon_service(db: DatabaseDep) -> ClassWeaponService:
    """Get the class weapon-proficiencies service instance."""

    return ClassWeaponService(db)


ClassWeaponsDep = Annotated[ClassWeaponService, Depends(get_class_weapon_service)]


def get_class_throws_service(db: DatabaseDep) -> ClassThrowsService:
    """Get the class saving-throws service instance."""

    return ClassThrowsService(db)


ClassThrowsDep = Annotated[ClassThrowsService, Depends(get_class_throws_service)]


def get_class_progression_service(db: DatabaseDep) -> ClassProgressionService:
    """Get the class progression service instance."""

    return ClassProgressionService(db)


ClassProgressionDep = Annotated[ClassProgressionService, Depends(get_class_progression_service)]
