"""Per-capability dependency providers for the features domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.features.crud.service import FeatureCrudService
from app.features.features.effects.service import FeatureEffectsService


def get_feature_crud_service(db: DatabaseDep) -> FeatureCrudService:
    """Get the feature CRUD service instance."""

    return FeatureCrudService(db)


FeatureCrudDep = Annotated[FeatureCrudService, Depends(get_feature_crud_service)]


def get_feature_effects_service(db: DatabaseDep) -> FeatureEffectsService:
    """Get the feature effect-engine service instance."""

    return FeatureEffectsService(db)


FeatureEffectsDep = Annotated[FeatureEffectsService, Depends(get_feature_effects_service)]
