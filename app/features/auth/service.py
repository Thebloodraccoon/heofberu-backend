from fastapi import Response
from sqlalchemy.orm import Session

from app.constants import UserRole
from app.core.exceptions import InvalidCredentialsException, InvalidTokenException
from app.core.security import get_password_hash, verify_password
from app.core.token_utils import (
    DecodedToken,
    blacklist_token,
    create_access_token,
    create_refresh_token,
    is_token_blacklisted,
    verify_refresh_token,
)
from app.features.auth.schemas import (
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
)
from app.features.users.exceptions import UserEmailAlreadyExistsException, UserNameAlreadyExistsException
from app.features.users.repository import UserRepository

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


class AuthService:
    def __init__(self, db: Session):
        self.user_repo = UserRepository(db)

    def login(self, request: LoginRequest, response: Response) -> LoginResponse:
        """Verify credentials, issue a fresh access/refresh token pair, and set the refresh cookie."""

        user = self.user_repo.get_by_email(request.email)

        if not user or not verify_password(request.password, str(user.hashed_password)):
            raise InvalidCredentialsException()

        updated_user = self.user_repo.update_last_login(user)
        return LoginResponse(access_token=self._issue_tokens(updated_user.email, response))

    def register(self, request: RegisterRequest, response: Response) -> RegisterResponse:
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
        """

        self._check_email_available(request.email)
        self._check_username_available(request.username)

        user_data = {
            "username": request.username,
            "email": request.email,
            "role": UserRole.PLAYER,
            "hashed_password": get_password_hash(request.password),
        }
        user = self.user_repo.create(user_data)

        return RegisterResponse(access_token=self._issue_tokens(user.email, response))

    def refresh_tokens(self, refresh_token: str) -> RefreshResponse:
        """
        Issue a new access token from a valid, non-revoked refresh token.

        The refresh token itself is only *checked* against the blacklist
        here, not consumed/rotated — logout is what blacklists it (see
        ``logout``). A revoked refresh token (e.g. from a completed
        logout) is rejected the same as an invalid or expired one, so a
        stolen refresh token can't outlive an explicit logout.
        """
        decoded = verify_refresh_token(refresh_token)

        if is_token_blacklisted(decoded.jti):
            raise InvalidCredentialsException()

        user = self.user_repo.get_by_email(decoded.email)
        if not user:
            raise InvalidCredentialsException()

        new_access_token = create_access_token(data={"sub": user.email})
        return RefreshResponse(access_token=new_access_token)

    def logout(self, access_token: DecodedToken, refresh_token_str: str | None) -> LogoutResponse:
        """
        Revoke the current access token and, if present, the refresh
        token cookie — both immediately unusable rather than left to
        expire naturally.

        ``access_token`` is the already-verified token behind the
        request (from ``CurrentUserDep`` — see ``endpoints.logout``), so
        no re-verification happens here. ``refresh_token_str`` is read
        directly from the request cookie; a missing/invalid one is
        tolerated (nothing to revoke, and a user who already lost their
        refresh cookie shouldn't be blocked from logging out the access
        token they do have).
        """

        blacklist_token(access_token.jti, access_token.remaining_seconds, reason="logout")

        if refresh_token_str:
            try:
                decoded_refresh = verify_refresh_token(refresh_token_str)
            except InvalidTokenException:
                pass
            else:
                blacklist_token(decoded_refresh.jti, decoded_refresh.remaining_seconds, reason="logout")

        return LogoutResponse(detail="Successful logout")

    def _check_email_available(self, email: str) -> None:
        """Raise ``UserEmailAlreadyExistsException`` if ``email`` is already taken."""

        if self.user_repo.get_by_email(email):
            raise UserEmailAlreadyExistsException(email)

    def _check_username_available(self, username: str) -> None:
        """Raise ``UserNameAlreadyExistsException`` if ``username`` is already taken."""

        if self.user_repo.get_by_username(username):
            raise UserNameAlreadyExistsException(name=username)

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
