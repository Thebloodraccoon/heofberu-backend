"""Per-capability dependency providers for the feats domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.feats.crud.service import FeatCrudService


def get_feat_crud_service(db: DatabaseDep) -> FeatCrudService:
    """Get the feat CRUD service instance."""

    return FeatCrudService(db)


FeatCrudDep = Annotated[FeatCrudService, Depends(get_feat_crud_service)]


async def require_feat(feature_id: int, feat_service: FeatCrudDep) -> None:
    """Route guard for the effects endpoints mounted under ``/feats``: 404 unless ``feature_id`` is a feat."""

    await feat_service.ensure_exists(feature_id)
