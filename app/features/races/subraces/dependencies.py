"""Per-capability dependency providers for the subrace subdomain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.races.subraces.ability_bonuses.service import SubraceAbilityBonusService
from app.features.races.subraces.crud.service import SubraceCrudService
from app.features.races.subraces.features.service import SubraceFeatureService


def get_subrace_crud_service(db: DatabaseDep) -> SubraceCrudService:
    """Get the subrace CRUD service instance."""

    return SubraceCrudService(db)


SubraceCrudDep = Annotated[SubraceCrudService, Depends(get_subrace_crud_service)]


def get_subrace_feature_service(db: DatabaseDep) -> SubraceFeatureService:
    """Get the subrace feature service instance."""

    return SubraceFeatureService(db)


SubraceFeaturesDep = Annotated[SubraceFeatureService, Depends(get_subrace_feature_service)]


def get_subrace_ability_bonus_service(db: DatabaseDep) -> SubraceAbilityBonusService:
    """Get the subrace ability-bonuses service instance."""

    return SubraceAbilityBonusService(db)


SubraceAbilityBonusesDep = Annotated[SubraceAbilityBonusService, Depends(get_subrace_ability_bonus_service)]
