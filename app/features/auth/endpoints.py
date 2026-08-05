"""Auth endpoints: register, login, logout, refresh."""

from fastapi import APIRouter, Request, Response, status

from app.core.dependencies import AuthServiceDep, CurrentUserDep, TokenDep
from app.core.token_utils import verify_token
from app.features.auth.schemas import (
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
)
from app.features.auth.service import REFRESH_COOKIE_NAME

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, response: Response, auth_service: AuthServiceDep):
    """
    Publicly self-register a new account.

    Unauthenticated — anyone can call this. The new account is always
    created with the ``PLAYER`` role (see ``RegisterRequest``); creating
    a user with an arbitrary role still requires a GM via
    ``POST /users/``. On success, the caller is logged in immediately
    (access token in the response body, refresh token set as an
    httponly cookie), the same as ``/auth/login``.
    """
    return auth_service.register(request, response)


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, response: Response, auth_service: AuthServiceDep):
    """
    Log in with email and password.

    On success returns a new ``access_token`` and sets the refresh token
    as an httponly cookie on the response. ``InvalidCredentialsException``
    (401) on a bad email/password.
    """
    return auth_service.login(request, response)


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    token: TokenDep,
    auth_service: AuthServiceDep,
    _: CurrentUserDep,
):
    """
    Log out the current user, revoking both the access token behind this
    request and the refresh token cookie (if present) so neither can be
    used again, then clears the refresh cookie client-side.

    ``_: CurrentUserDep`` still gates this endpoint on a valid,
    non-blacklisted access token (see ``get_current_user``) — ``token``
    is decoded a second time here only to hand its ``jti``/expiry to
    ``AuthService.logout`` for revocation, not to re-authenticate.
    """

    decoded_access_token = verify_token(token, "access")
    refresh_token_str = request.cookies.get(REFRESH_COOKIE_NAME)

    logout_response = auth_service.logout(decoded_access_token, refresh_token_str)
    response.delete_cookie(key=REFRESH_COOKIE_NAME, httponly=True, samesite="none", secure=True)

    return logout_response


@router.post("/refresh", response_model=RefreshResponse)
def refresh_tokens(http_request: Request, auth_service: AuthServiceDep):
    """
    Exchange the refresh-token cookie for a fresh access token.

    Requires a valid, non-revoked refresh token in the ``refresh_token``
    cookie; otherwise raises ``InvalidCredentialsException`` (401).
    """
    refresh_token = http_request.cookies.get(REFRESH_COOKIE_NAME, "")
    return auth_service.refresh_tokens(refresh_token)
