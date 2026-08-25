"""Per-capability dependency providers for the features domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.features.ability_increases.service import FeatureAbilityIncreaseService
from app.features.features.crud.service import FeatureCrudService


def get_feature_crud_service(db: DatabaseDep) -> FeatureCrudService:
    """Get the feature CRUD service instance."""

    return FeatureCrudService(db)


FeatureCrudDep = Annotated[FeatureCrudService, Depends(get_feature_crud_service)]


def get_feature_ability_increase_service(db: DatabaseDep) -> FeatureAbilityIncreaseService:
    """Get the feature ability-increase service instance."""

    return FeatureAbilityIncreaseService(db)


FeatureAbilityIncreasesDep = Annotated[FeatureAbilityIncreaseService, Depends(get_feature_ability_increase_service)]
