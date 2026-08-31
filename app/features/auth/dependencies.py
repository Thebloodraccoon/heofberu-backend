"""Per-feature dependency providers for the auth domain."""

from typing import Annotated

from fastapi import Depends

from app.core.db import DatabaseDep
from app.core.email.dependencies import EmailServiceDep
from app.features.auth.service import AuthService


def get_auth_service(db: DatabaseDep, email_service: EmailServiceDep) -> AuthService:
    """Get the auth service instance."""

    return AuthService(db, email_service=email_service)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
