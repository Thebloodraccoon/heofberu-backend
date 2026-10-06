"""Per-capability dependency providers for the spells domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.spells.availability.service import SpellAvailabilityService
from app.features.spells.crud.service import SpellCrudService


def get_spell_crud_service(db: DatabaseDep) -> SpellCrudService:
    """Build the spell CRUD service instance."""

    return SpellCrudService(db)


SpellCrudDep = Annotated[SpellCrudService, Depends(get_spell_crud_service)]


def get_spell_availability_service(db: DatabaseDep) -> SpellAvailabilityService:
    """Build the spell availability service instance."""

    return SpellAvailabilityService(db)


SpellAvailabilityDep = Annotated[SpellAvailabilityService, Depends(get_spell_availability_service)]
