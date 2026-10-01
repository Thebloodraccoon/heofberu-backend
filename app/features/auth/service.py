"""Business logic for authentication: login, registration, token refresh, logout, password reset."""

from fastapi import BackgroundTasks, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import UserRole
from app.core.background import add_safe_task
from app.core.base.transaction import atomic
from app.core.email.service import EmailService
from app.core.exceptions import (
    InvalidCredentialsException,
    InvalidTokenException,
    RecordAlreadyExistsError,
)
from app.core.security.password import get_password_hash_async, verify_password_async
from app.core.security.token import (
    blacklist_token,
    create_access_token,
    create_refresh_token,
    create_reset_token,
    verify_refresh_token,
    verify_reset_token,
    verify_token,
)
from app.features.auth.exceptions import AccountAlreadyExistsException, InvalidResetTokenException
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
from app.features.auth.sessions import claim_token, is_session_revoked, release_token, revoke_user_sessions
from app.features.users.repository import UserRepository
from app.features.users.service import invalidate_user_cache

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
_REFRESH_COOKIE_ATTRIBUTES = {"httponly": True, "samesite": "none", "secure": True, "path": "/api/v1/auth"}

# A dummy bcrypt hash equalizes login timing so unknown emails can't be told apart from wrong passwords.
DUMMY_PASSWORD_HASH = "$2b$12$DwWynkIMMBTtbcY8mPXP8ukj.AwYLuoe.xsvr8/XZNjHDfPrWS25i"  # nosec B105 -- not a credential: public constant hash used as a timing-equalizing dummy


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Attach the refresh token as the httpOnly cookie scoped to the auth endpoints."""

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=REFRESH_COOKIE_MAX_AGE_SECONDS,
        **_REFRESH_COOKIE_ATTRIBUTES,
    )


def delete_refresh_cookie(response: Response) -> None:
    """Expire the refresh cookie, using the exact attributes it was set with."""

    response.delete_cookie(key=REFRESH_COOKIE_NAME, **_REFRESH_COOKIE_ATTRIBUTES)


class AuthService:
    """
    Orchestrates login, registration, token refresh, logout, and password reset.

    Token ``sub`` is the immutable user id (legacy email subjects are still
    accepted). Refresh tokens rotate: each use claims the old ``jti``
    atomically and issues a new cookie. A password reset revokes every
    token issued before it.
    """

    def __init__(self, db: AsyncSession, email_service: EmailService):
        """Wire up the user repository and the email service."""

        self.db = db
        self.user_repo = UserRepository(db)
        self.email_service = email_service

    async def login(self, request: LoginRequest, response: Response) -> LoginResponse:
        """Verify credentials, issue a fresh access/refresh token pair, and set the refresh cookie."""

        user = await self.user_repo.get_by_email(request.email)

        password_hash = str(user.hashed_password) if user else DUMMY_PASSWORD_HASH
        if not user or not await verify_password_async(request.password, password_hash):
            raise InvalidCredentialsException()

        await self.user_repo.update_last_login(user.id)
        await invalidate_user_cache(self.db, user.id)

        return LoginResponse(access_token=self._issue_tokens(user.id, response))

    async def register(self, request: RegisterRequest, response: Response) -> RegisterResponse:
        """Create a new self-registered PLAYER account and log it in immediately."""

        user_data = {
            "username": request.username,
            "email": request.email,
            "role": UserRole.PLAYER,
            "hashed_password": await get_password_hash_async(request.password),
        }
        try:
            user = await self.user_repo.create(user_data)
        except RecordAlreadyExistsError:
            raise AccountAlreadyExistsException() from None

        return RegisterResponse(access_token=self._issue_tokens(user.id, response))

    async def refresh_tokens(self, refresh_token: str, response: Response) -> RefreshResponse:
        """
        Rotate the refresh token: issue a new access token and a new refresh cookie.

        The presented token's ``jti`` is claimed atomically, so it works
        exactly once; a replayed or logged-out token is rejected. Tokens
        issued before the user's last password reset are rejected too.
        """

        decoded = verify_refresh_token(refresh_token)

        user = await self.user_repo.get_by_subject(decoded.subject)
        if not user:
            raise InvalidCredentialsException()

        if await is_session_revoked(decoded, user.id):
            raise InvalidCredentialsException()

        if not await claim_token(decoded.jti, decoded.remaining_seconds, reason="refresh_rotated"):
            raise InvalidCredentialsException()

        return RefreshResponse(access_token=self._issue_tokens(user.id, response))

    async def forgot_password(
        self, request: ForgotPasswordRequest, background_tasks: BackgroundTasks
    ) -> ForgotPasswordResponse:
        """
        Queue a short-lived reset token by email; returns the same response
        whether or not the account exists. The SMTP round trip runs after
        the response is sent, so timing does not reveal the account either.
        """

        user = await self.user_repo.get_by_email(request.email)

        if user:
            reset_token = create_reset_token(data={"sub": str(user.id)})
            add_safe_task(background_tasks, self.email_service.send_password_reset, user.email, reset_token)

        return ForgotPasswordResponse(
            detail="If an account with this email exists, a password reset link has been sent."
        )

    async def reset_password(self, request: ResetPasswordRequest) -> ResetPasswordResponse:
        """
        Set a new password using a valid reset token and revoke the user's sessions.

        The token is claimed with an atomic ``SET NX`` before anything
        changes, so concurrent or replayed requests cannot both succeed; the
        claim is released if the update fails, letting the user retry.
        """

        try:
            decoded = verify_reset_token(request.token)
        except InvalidTokenException:
            raise InvalidResetTokenException() from None

        user = await self.user_repo.get_by_subject(decoded.subject)
        if not user or await is_session_revoked(decoded, user.id):
            raise InvalidResetTokenException()

        if not await claim_token(decoded.jti, decoded.remaining_seconds, reason="password_reset"):
            raise InvalidResetTokenException()

        try:
            new_hash = await get_password_hash_async(request.new_password)
            async with atomic(self.db):
                user.hashed_password = new_hash  # type: ignore[assignment]
            await revoke_user_sessions(user.id)
        except Exception:
            await release_token(decoded.jti)
            raise

        return ResetPasswordResponse(detail="Password has been reset. You can now log in.")

    @staticmethod
    async def logout(
        access_token: HTTPAuthorizationCredentials | None,
        refresh_token_str: str | None,
    ) -> LogoutResponse:
        """
        Revoke the access token and, if present, the refresh cookie so both
        are immediately unusable. A missing/invalid refresh token is tolerated.
        """

        decoded_access_token = verify_token(access_token, "access")
        await blacklist_token(decoded_access_token.jti, decoded_access_token.remaining_seconds, reason="logout")

        if refresh_token_str:
            try:
                decoded_refresh = verify_refresh_token(refresh_token_str)
            except InvalidTokenException:
                pass
            else:
                await blacklist_token(decoded_refresh.jti, decoded_refresh.remaining_seconds, reason="logout")

        return LogoutResponse(detail="Successful logout")

    @staticmethod
    def _issue_tokens(user_id: int, response: Response) -> str:
        """Create an access/refresh pair for ``user_id``, set the refresh cookie, return the access token."""

        claims = {"sub": str(user_id)}
        set_refresh_cookie(response, create_refresh_token(data=claims))

        return create_access_token(data=claims)
