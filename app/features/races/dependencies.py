"""Per-capability dependency providers for the races domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.races.ability_bonuses.service import RaceAbilityBonusService
from app.features.races.crud.service import RaceCrudService
from app.features.races.features.service import RaceFeatureService
from app.features.races.skills.service import RaceSkillService


def get_race_crud_service(db: DatabaseDep) -> RaceCrudService:
    """Get the race CRUD service instance."""

    return RaceCrudService(db)


RaceCrudDep = Annotated[RaceCrudService, Depends(get_race_crud_service)]


def get_race_feature_service(db: DatabaseDep) -> RaceFeatureService:
    """Get the race feature service instance."""

    return RaceFeatureService(db)


RaceFeaturesDep = Annotated[RaceFeatureService, Depends(get_race_feature_service)]


def get_race_skill_service(db: DatabaseDep) -> RaceSkillService:
    """Get the race skills service instance."""

    return RaceSkillService(db)


RaceSkillsDep = Annotated[RaceSkillService, Depends(get_race_skill_service)]


def get_race_ability_bonus_service(db: DatabaseDep) -> RaceAbilityBonusService:
    """Get the race ability-bonuses service instance."""

    return RaceAbilityBonusService(db)


RaceAbilityBonusesDep = Annotated[RaceAbilityBonusService, Depends(get_race_ability_bonus_service)]
