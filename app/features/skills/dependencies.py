"""Per-capability dependency providers for the skills domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.skills.crud.service import SkillCrudService


def get_skill_crud_service(db: DatabaseDep) -> SkillCrudService:
    """Get the skill CRUD service instance."""

    return SkillCrudService(db)


SkillCrudDep = Annotated[SkillCrudService, Depends(get_skill_crud_service)]
