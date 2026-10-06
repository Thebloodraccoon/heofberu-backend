"""Per-capability dependency providers for the tags domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.tags.crud.service import TagCrudService


def get_tag_crud_service(db: DatabaseDep) -> TagCrudService:
    """Build the tag CRUD service instance."""

    return TagCrudService(db)


TagCrudDep = Annotated[TagCrudService, Depends(get_tag_crud_service)]
