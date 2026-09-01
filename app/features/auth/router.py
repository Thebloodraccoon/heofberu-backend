"""Auth endpoints: register, login, logout, refresh."""

from typing import Annotated

from fastapi import APIRouter, Body, Request, Response, status

from app.features.auth.dependencies import AuthServiceDep
from app.features.auth.schemas import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
)
from app.features.auth.service import REFRESH_COOKIE_NAME
from app.features.users.security import CurrentUserDep, TokenDep

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Self-register a new account",
    responses={
        400: {"description": "An account with this email or username already exists; invalid email; or weak password."},
        422: {"description": "Validation error — username length/charset or request body shape is invalid."},
    },
)
async def register(
    response: Response,
    data: Annotated[
        RegisterRequest,
        Body(
            openapi_examples={
                "player": {
                    "summary": "Typical new player",
                    "value": {
                        "username": "aria_of_the_vale",
                        "email": "aria@example.com",
                        "password": "correct-horse-battery",
                    },
                },
                "minimal": {
                    "summary": "Minimal — only required fields",
                    "value": {
                        "username": "borin",
                        "email": "borin@example.com",
                        "password": "sturdy-passphrase-1",
                    },
                },
            },
        ),
    ],
    auth_service: AuthServiceDep,
):
    """Self-register a new account and log it in immediately. Open endpoint."""

    return await auth_service.register(data, response)


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Log in",
    responses={
        400: {"description": "Email fails validation."},
        401: {"description": "Invalid email or password."},
        422: {"description": "Validation error — email format or request body shape is invalid."},
    },
)
async def login(
    response: Response,
    data: Annotated[
        LoginRequest,
        Body(
            openapi_examples={
                "player": {
                    "summary": "Player credentials",
                    "value": {
                        "email": "aria@example.com",
                        "password": "correct-horse-battery",
                    },
                },
                "gm": {
                    "summary": "GM credentials",
                    "value": {
                        "email": "gm@table.example.com",
                        "password": "behind-the-screen",
                    },
                },
            },
        ),
    ],
    auth_service: AuthServiceDep,
):
    """Log in with email and password, setting the refresh cookie. Open endpoint."""

    return await auth_service.login(data, response)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Log out the current user",
    responses={
        401: {"description": "Access token missing, malformed, expired, blacklisted, or of the wrong type."},
    },
)
async def logout(
    request: Request,
    response: Response,
    auth_service: AuthServiceDep,
    token: TokenDep,
    _: CurrentUserDep,
):
    """Log out, revoking the access token and refresh cookie. **Authenticated.**"""

    refresh_token_str = request.cookies.get(REFRESH_COOKIE_NAME)

    logout_response = await auth_service.logout(token, refresh_token_str)
    response.delete_cookie(key=REFRESH_COOKIE_NAME, httponly=True, samesite="none", secure=True)

    return logout_response


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Refresh the access token",
    responses={
        401: {"description": "Refresh cookie missing, invalid, expired, or revoked (e.g. by a prior logout)."},
    },
)
async def refresh_tokens(http_request: Request, auth_service: AuthServiceDep):
    """Exchange the refresh-token cookie for a fresh access token. Open endpoint."""

    refresh_token = http_request.cookies.get(REFRESH_COOKIE_NAME, "")
    return await auth_service.refresh_tokens(refresh_token)


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    summary="Request a password reset link by email",
    responses={
        400: {"description": "Email fails validation."},
        422: {"description": "Validation error — email format is invalid."},
    },
)
async def forgot_password(
    data: Annotated[
        ForgotPasswordRequest,
        Body(
            openapi_examples={
                "player": {
                    "summary": "Request a reset link",
                    "value": {
                        "email": "aria@example.com",
                    },
                },
            },
        ),
    ],
    auth_service: AuthServiceDep,
):
    """Request a password-reset email; neutral response prevents enumeration. Open endpoint."""

    return await auth_service.forgot_password(data)


@router.post(
    "/reset-password",
    response_model=ResetPasswordResponse,
    summary="Set a new password using the emailed reset token",
    responses={
        400: {"description": "Reset token invalid/expired/used, weak password, or passwords do not match."},
        422: {"description": "Validation error — body shape is invalid."},
    },
)
async def reset_password(
    data: Annotated[
        ResetPasswordRequest,
        Body(
            openapi_examples={
                "player": {
                    "summary": "Set a new password",
                    "value": {
                        "token": "<token-from-email-link>",
                        "new_password": "correct-horse-battery",
                        "confirm_password": "correct-horse-battery",
                    },
                },
            },
        ),
    ],
    auth_service: AuthServiceDep,
):
    """Set a new password using the emailed reset token. Open endpoint."""

    return await auth_service.reset_password(data)
