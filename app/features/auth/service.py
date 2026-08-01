from fastapi import Response
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidCredentialsException
from app.core.security import verify_password
from app.features.auth.schemas import LoginRequest, LoginResponse, LogoutResponse, RefreshResponse
from app.features.auth.token_utils import create_access_token, create_refresh_token, verify_refresh_token
from app.features.users.repository import UserRepository


def create_login_response(user, response: Response) -> LoginResponse:
    """Create login response with tokens and cookies."""
    access_token = create_access_token(data={"sub": user.email})
    refresh_token = create_refresh_token(data={"sub": user.email})

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="none",
        secure=True,
        max_age=30 * 24 * 60 * 60,
    )

    return LoginResponse(access_token=access_token)


class AuthService:
    def __init__(self, db: Session):
        self.user_repo = UserRepository(db)

    def login(self, request: LoginRequest, response: Response) -> LoginResponse:
        """Handle login and issue tokens."""
        user = self.user_repo.get_by_email(request.email)

        if not user or not verify_password(request.password, str(user.hashed_password)):
            raise InvalidCredentialsException()

        updated_user = self.user_repo.update_last_login(user)
        return create_login_response(updated_user, response)

    def refresh_tokens(self, refresh_token: str) -> RefreshResponse:
        """Issue a new access token from a valid refresh token."""
        email = verify_refresh_token(refresh_token)
        user = self.user_repo.get_by_email(email)

        if not user:
            raise InvalidCredentialsException()

        new_access_token = create_access_token(data={"sub": user.email})
        return RefreshResponse(access_token=new_access_token)

    @classmethod
    def logout_user(cls) -> LogoutResponse:
        """Clear client-side session. Access tokens naturally expire; no server-side revocation."""
        return LogoutResponse(detail="Successful logout")
