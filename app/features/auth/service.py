from fastapi import Response
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidCredentialsException, InvalidTokenException
from app.core.security import verify_password
from app.core.token_utils import verify_refresh_token, is_token_blacklisted, create_access_token, DecodedToken, \
    blacklist_token, create_refresh_token
from app.features.auth.schemas import LoginRequest, LoginResponse, LogoutResponse, RefreshResponse
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
        return self._issue_tokens(updated_user.email, response)

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

    @staticmethod
    def _issue_tokens(email: str, response: Response) -> LoginResponse:
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

        return LoginResponse(access_token=access_token)