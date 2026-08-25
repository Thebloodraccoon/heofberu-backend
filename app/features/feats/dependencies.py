"""Per-capability dependency providers for the feats domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.feats.asi.service import FeatAsiService
from app.features.feats.crud.service import FeatCrudService


def get_feat_crud_service(db: DatabaseDep) -> FeatCrudService:
    """Get the feat CRUD service instance."""

    return FeatCrudService(db)


FeatCrudDep = Annotated[FeatCrudService, Depends(get_feat_crud_service)]


def get_feat_asi_service(db: DatabaseDep) -> FeatAsiService:
    """Get the feat ASI service instance."""

    return FeatAsiService(db)


FeatAsiDep = Annotated[FeatAsiService, Depends(get_feat_asi_service)]
