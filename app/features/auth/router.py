"""Auth endpoints: register, login, logout, refresh, forgot/reset password."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Body, Request, Response, status

from app.features.auth.dependencies import AuthServiceDep, CurrentUserDep, TokenDep
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
from app.features.auth.service import delete_refresh_cookie, read_refresh_cookie

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Self-register a new account",
    responses={
        400: {"description": "Invalid email or weak password."},
        409: {"description": "An account with this email or username already exists."},
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

    refresh_token_str = read_refresh_cookie(request)

    logout_response = await auth_service.logout(token, refresh_token_str)
    delete_refresh_cookie(response)

    return logout_response


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Refresh the access token",
    responses={
        401: {
            "description": (
                "Refresh cookie missing, invalid, expired, already used, or revoked "
                "(by a prior logout, rotation or password reset)."
            )
        },
    },
)
async def refresh_tokens(http_request: Request, response: Response, auth_service: AuthServiceDep):
    """Rotate the refresh-token cookie: returns a fresh access token and sets a new refresh cookie. Open endpoint."""

    refresh_token = read_refresh_cookie(http_request) or ""
    return await auth_service.refresh_tokens(refresh_token, response)


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
    background_tasks: BackgroundTasks,
):
    """Request a password-reset email; neutral response prevents enumeration. Open endpoint."""

    return await auth_service.forgot_password(data, background_tasks)


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
