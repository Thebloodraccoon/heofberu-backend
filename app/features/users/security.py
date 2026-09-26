"""Auth/authz dependency providers, kept in ``users`` so dependency arrows point into it (no layering inversion)."""

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
    Resolve the user from the bearer token, validating signature/expiry
    and rejecting blacklisted tokens.
    """

    decoded = verify_token(token, "access")

    if await is_token_blacklisted(decoded.jti):
        raise InvalidTokenException()

    return await user_service.get_user_by_email(decoded.email)


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
