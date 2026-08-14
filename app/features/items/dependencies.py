"""Per-capability dependency providers for the items domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.items.crud.service import ItemCrudService


def get_item_crud_service(db: DatabaseDep) -> ItemCrudService:
    """Get the item CRUD service instance."""

    return ItemCrudService(db)


ItemCrudDep = Annotated[ItemCrudService, Depends(get_item_crud_service)]
