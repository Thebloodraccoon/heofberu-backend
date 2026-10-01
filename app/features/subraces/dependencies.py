"""Per-capability dependency providers for the subrace subdomain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.core.storage.dependencies import StorageServiceDep
from app.features.subraces.ability_bonuses.service import SubraceAbilityBonusService
from app.features.subraces.crud.service import SubraceCrudService
from app.features.subraces.features.service import SubraceFeatureService
from app.features.subraces.image.service import SubraceImageService
from app.features.subraces.tags.service import SubraceTagService


def get_subrace_crud_service(db: DatabaseDep, storage: StorageServiceDep) -> SubraceCrudService:
    """Get the subrace CRUD service instance."""

    return SubraceCrudService(db, storage)


SubraceCrudDep = Annotated[SubraceCrudService, Depends(get_subrace_crud_service)]


def get_subrace_feature_service(db: DatabaseDep) -> SubraceFeatureService:
    """Get the subrace feature service instance."""

    return SubraceFeatureService(db)


SubraceFeaturesDep = Annotated[SubraceFeatureService, Depends(get_subrace_feature_service)]


def get_subrace_ability_bonus_service(db: DatabaseDep) -> SubraceAbilityBonusService:
    """Get the subrace ability-bonuses service instance."""

    return SubraceAbilityBonusService(db)


SubraceAbilityBonusesDep = Annotated[SubraceAbilityBonusService, Depends(get_subrace_ability_bonus_service)]


def get_subrace_image_service(db: DatabaseDep, storage: StorageServiceDep) -> SubraceImageService:
    """Get the subrace image service instance."""

    return SubraceImageService(db, storage)


SubraceImageDep = Annotated[SubraceImageService, Depends(get_subrace_image_service)]


def get_subrace_tag_service(db: DatabaseDep) -> SubraceTagService:
    """Get the subrace tags service instance."""

    return SubraceTagService(db)


SubraceTagsDep = Annotated[SubraceTagService, Depends(get_subrace_tag_service)]
