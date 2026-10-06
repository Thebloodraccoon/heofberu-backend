"""Per-capability dependency providers for the classes domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.core.storage.dependencies import StorageServiceDep
from app.features.classes.crud.service import ClassCrudService
from app.features.classes.features.service import ClassFeatureService
from app.features.classes.image.service import ClassImageService
from app.features.classes.items.service import ClassItemsService
from app.features.classes.proficiencies.service import ClassProficiencyService
from app.features.classes.progression.service import ClassProgressionService
from app.features.classes.skills.service import ClassSkillService


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


def get_class_proficiency_service(db: DatabaseDep) -> ClassProficiencyService:
    """Get the class proficiency (saving throws / armor / weapons) service instance."""

    return ClassProficiencyService(db)


ClassProficienciesDep = Annotated[ClassProficiencyService, Depends(get_class_proficiency_service)]


def get_class_progression_service(db: DatabaseDep) -> ClassProgressionService:
    """Get the class progression service instance."""

    return ClassProgressionService(db)


ClassProgressionDep = Annotated[ClassProgressionService, Depends(get_class_progression_service)]


def get_class_image_service(db: DatabaseDep, storage: StorageServiceDep) -> ClassImageService:
    """Get the class image service instance."""

    return ClassImageService(db, storage)


ClassImageDep = Annotated[ClassImageService, Depends(get_class_image_service)]
