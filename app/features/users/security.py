"""
Authentication/authorization dependency providers.

Lives in the ``users`` domain (not ``core``): resolving the current user
requires the users service, so every dependency arrow points INTO
``users`` and no layering inversion (core importing a feature) occurs.
Everything cryptographic stays generic in ``app/core/security/token.py``.
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.constants import UserRole
from app.core.exceptions import FoundFatherAccessException, GmAccessException, InvalidTokenException
from app.core.security.token import is_token_blacklisted, verify_token
from app.features.users.dependencies import UserServiceDep
from app.features.users.schemas import UserResponse

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
    Resolve the authenticated user from the bearer token.

    Validates the token signature/expiry, rejects blacklisted tokens, and
    returns the matching user, raising ``InvalidTokenException`` otherwise.
    """

    decoded = verify_token(token, "access")

    if await is_token_blacklisted(decoded.jti):
        raise InvalidTokenException()

    return await user_service.get_user_by_email(decoded.email)


CurrentUserDep = Annotated[UserResponse, Depends(get_current_user)]


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
