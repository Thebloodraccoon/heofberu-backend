"""Per-capability dependency providers for the subclass subdomain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.subclasses.crud.service import SubclassCrudService
from app.features.subclasses.features.service import SubclassFeatureService


def get_subclass_crud_service(db: DatabaseDep) -> SubclassCrudService:
    """Get the subclass CRUD service instance."""

    return SubclassCrudService(db)


SubclassCrudDep = Annotated[SubclassCrudService, Depends(get_subclass_crud_service)]


def get_subclass_feature_service(db: DatabaseDep) -> SubclassFeatureService:
    """Get the subclass feature service instance."""

    return SubclassFeatureService(db)


SubclassFeaturesDep = Annotated[SubclassFeatureService, Depends(get_subclass_feature_service)]
