"""Business logic for authentication: login, registration, token refresh, logout, password reset."""

from fastapi import Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import UserRole
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
    is_token_blacklisted,
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
from app.features.users.repository import UserRepository

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60

# A throwaway bcrypt hash used to equalize login timing: when no user
# exists for a given email, we still run verify_password against this
# dummy hash so a request for an unknown email takes roughly as long as
# one for an existing account with a wrong password. Without this, an
# attacker could distinguish "no such account" from "wrong password" by
# timing alone, and use that to enumerate registered emails.
DUMMY_PASSWORD_HASH = "$2b$12$DwWynkIMMBTtbcY8mPXP8ukj.AwYLuoe.xsvr8/XZNjHDfPrWS25i"  # nosec B105 -- not a credential: public constant hash used as a timing-equalizing dummy


class AuthService:
    """Orchestrates login, registration, token refresh, logout, and password reset."""

    def __init__(self, db: AsyncSession, email_service: EmailService | None = None):
        self.user_repo = UserRepository(db)
        self.email_service = email_service or EmailService()

    async def login(self, request: LoginRequest, response: Response) -> LoginResponse:
        """Verify credentials, issue a fresh access/refresh token pair, and set the refresh cookie."""

        user = await self.user_repo.get_by_email(request.email)

        password_hash = str(user.hashed_password) if user else DUMMY_PASSWORD_HASH
        if not user or not await verify_password_async(request.password, password_hash):
            raise InvalidCredentialsException()

        updated_user = await self.user_repo.update_last_login(user)
        return LoginResponse(access_token=self._issue_tokens(updated_user.email, response))

    async def register(self, request: RegisterRequest, response: Response) -> RegisterResponse:
        """
        Create a new self-registered account and immediately log it in.

        Unlike the GM-only ``UserService.create_user``, the new account:
          - is always created with ``UserRole.PLAYER``, regardless of
            anything the caller sends (``RegisterRequest`` has no
            ``role`` field at all, so there's nothing to trust here);
          - is logged in on success, the same as ``login`` — the caller
            gets back an ``access_token`` and has the refresh cookie set
            on ``response``, instead of having to call ``/auth/login``
            as a separate follow-up step.

        Email/username uniqueness is checked up front so this fails with
        a clear 400 before hitting the database's own unique constraint.
        The duplicate-account error is deliberately generic — the raw
        ``RecordAlreadyExistsError`` echoes the offending email in its
        message, which would let anyone confirm whether an address is
        already registered. Re-raising with a neutral detail keeps the
        400 without leaking account existence.
        """

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

        return RegisterResponse(access_token=self._issue_tokens(user.email, response))

    async def refresh_tokens(self, refresh_token: str) -> RefreshResponse:
        """
        Issue a new access token from a valid, non-revoked refresh token.

        The refresh token itself is only *checked* against the blacklist
        here, not consumed/rotated — logout is what blacklists it (see
        ``logout``). A revoked refresh token (e.g. from a completed
        logout) is rejected the same as an invalid or expired one, so a
        stolen refresh token can't outlive an explicit logout.
        """

        decoded = verify_refresh_token(refresh_token)

        if await is_token_blacklisted(decoded.jti):
            raise InvalidCredentialsException()

        user = await self.user_repo.get_by_email(decoded.email)
        if not user:
            raise InvalidCredentialsException()

        new_access_token = create_access_token(data={"sub": user.email})
        return RefreshResponse(access_token=new_access_token)

    async def forgot_password(self, request: ForgotPasswordRequest) -> ForgotPasswordResponse:
        """
        Issue a short-lived reset token for the account and email it.

        Deliberately returns the same response whether or not the email
        exists, so the endpoint cannot be used to enumerate registered
        addresses (mirrors the timing-equalizing approach in ``login``).

        The emailed link is built by the email service from its hardcoded
        reset page URL plus the token (see ``RESET_BASE_URL``). Sending is
        best-effort: a failed SMTP round-trip is logged by the email
        service and never surfaces as an error here.
        """

        user = await self.user_repo.get_by_email(request.email)

        if user:
            reset_token = create_reset_token(data={"sub": request.email})
            await self.email_service.send_password_reset(request.email, reset_token)

        return ForgotPasswordResponse(
            detail="If an account with this email exists, a password reset link has been sent."
        )

    async def reset_password(self, request: ResetPasswordRequest) -> ResetPasswordResponse:
        """
        Set a new password using a valid, unused reset token.

        The token is a short-lived ``reset`` JWT (15 min). After the
        password is updated the token's ``jti`` is blacklisted, so the same
        link cannot be replayed. Any invalid/expired/reused token raises
        ``InvalidResetTokenException`` (400).
        """

        try:
            decoded = verify_reset_token(request.token)
        except InvalidTokenException:
            raise InvalidResetTokenException() from None

        if await is_token_blacklisted(decoded.jti):
            raise InvalidResetTokenException()

        user = await self.user_repo.get_by_email(decoded.email)
        if not user:
            raise InvalidResetTokenException()

        new_hash = await get_password_hash_async(request.new_password)
        user.hashed_password = new_hash  # type: ignore[assignment]
        await self.user_repo.commit_or_flush()

        await blacklist_token(decoded.jti, decoded.remaining_seconds, reason="password_reset")

        return ResetPasswordResponse(detail="Password has been reset. You can now log in.")

    @staticmethod
    async def logout(
        access_token: HTTPAuthorizationCredentials | None,
        refresh_token_str: str | None,
    ) -> LogoutResponse:
        """
        Revoke the current access token and, if present, the refresh
        token cookie — both immediately unusable rather than left to
        expire naturally.

        ``access_token`` is the raw bearer credentials behind the
        request; it is verified here (signature, expiry, ``access``
        type) before its ``jti``/TTL are used for blacklisting.
        ``refresh_token_str`` is read directly from the request cookie; a
        missing/invalid one is tolerated (nothing to revoke, and a user
        who already lost their refresh cookie shouldn't be blocked from
        logging out the access token they do have).
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
    def _issue_tokens(email: str, response: Response) -> str:
        """
        Create an access/refresh token pair for ``email``, set the refresh
        cookie on ``response``, and return the access token.

        Shared by ``login`` and ``register`` — both end with "issue a
        fresh token pair and log the caller in", differing only in how
        the underlying user was obtained/created.
        """

        access_token = create_access_token(data={"sub": email})
        refresh_token = create_refresh_token(data={"sub": email})

        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=refresh_token,
            httponly=True,
            samesite="none",
            secure=True,
            max_age=REFRESH_COOKIE_MAX_AGE_SECONDS,
        )

        return access_token
