"""
Dependency providers of the auth domain, shared by every feature router.

* ``AuthServiceDep`` — the auth service.
* ``TokenDep`` / ``CurrentUserDep`` / ``OptionalUserDep`` — resolve the bearer token to the current user.
* ``GmUserDep`` / ``FounderDep`` and ``can_see_hidden`` — role guards and predicate.

Feature routers import the user/role dependencies from here only. This module
depends on the users domain (service, schemas), never the other way round.
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.constants import UserRole
from app.core.db import DatabaseDep
from app.core.email.dependencies import EmailServiceDep
from app.core.exceptions import FoundFatherAccessException, GmAccessException, InvalidTokenException
from app.core.security.token import verify_token
from app.features.auth.service import AuthService
from app.features.auth.sessions import is_session_revoked
from app.features.users.dependencies import UserServiceDep
from app.features.users.exceptions import UserNotFoundException
from app.features.users.schemas import UserResponse


def get_auth_service(db: DatabaseDep, email_service: EmailServiceDep) -> AuthService:
    """Get the auth service instance."""

    return AuthService(db, email_service=email_service)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]

security = HTTPBearer(
    scheme_name="JWT Bearer",
    description="JWT Bearer token for authentication",
    auto_error=False,
)
TokenDep = Annotated[HTTPAuthorizationCredentials | None, Depends(security)]


async def get_current_user(
    user_service: UserServiceDep,
    token: TokenDep,
) -> UserResponse:
    """
    Resolve the user from the bearer token.

    Validates signature/expiry/type, rejects blacklisted tokens and tokens
    issued before the user's sessions were revoked, and answers 401 (never
    404) when the token's user no longer exists.
    """

    decoded = verify_token(token, "access")

    try:
        user_id = await user_service.resolve_subject_id(decoded.subject)
        if await is_session_revoked(decoded, user_id):
            raise InvalidTokenException()

        return await user_service.get_auth_user(user_id)
    except UserNotFoundException:
        raise InvalidTokenException() from None


CurrentUserDep = Annotated[UserResponse, Depends(get_current_user)]


async def get_optional_user(
    user_service: UserServiceDep,
    token: TokenDep,
) -> UserResponse | None:
    """
    Resolve the user when a bearer token is sent, or ``None`` for anonymous callers.

    For open endpoints whose payload depends on who's asking (e.g. hiding
    draft/GM-only articles). A token that IS sent but is invalid/expired/
    blacklisted still fails with 401 rather than silently downgrading to anonymous.
    """

    if token is None:
        return None

    return await get_current_user(user_service, token)


OptionalUserDep = Annotated[UserResponse | None, Depends(get_optional_user)]


def can_see_hidden(user: UserResponse | None) -> bool:
    """Whether ``user`` may see unpublished/GM-only content (GMs and the founder)."""

    return user is not None and user.role in (UserRole.GM, UserRole.FOUND_FATHER)


def require_gm(current_user: CurrentUserDep) -> UserResponse:
    """Require the current user to have the GM role (or the higher found-father role)."""

    if current_user.role not in (UserRole.GM, UserRole.FOUND_FATHER):
        raise GmAccessException()

    return current_user


GmUserDep = Annotated[UserResponse, Depends(require_gm)]


def require_found_father(current_user: CurrentUserDep) -> UserResponse:
    """Require the current user to have the found-father (founder) role."""

    if current_user.role != UserRole.FOUND_FATHER:
        raise FoundFatherAccessException()

    return current_user


FounderDep = Annotated[UserResponse, Depends(require_found_father)]
