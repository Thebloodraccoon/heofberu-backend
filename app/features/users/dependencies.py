"""Per-feature dependency providers for the users domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.users.service import UserService


def get_user_service(db: DatabaseDep) -> UserService:
    """Get the user service instance."""

    return UserService(db)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
