"""Per-feature dependency providers for the auth domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.features.auth.service import AuthService


def get_auth_service(db: DatabaseDep) -> AuthService:
    """Get the auth service instance."""

    return AuthService(db)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
