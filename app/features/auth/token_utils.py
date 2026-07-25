from datetime import datetime, timedelta, timezone

from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError, jwt

from app.exceptions.token_exceptions import InvalidTokenException
from app.settings import settings


def create_token(data: dict, token_type: str, expires_delta: timedelta) -> str:
    """Create JWT token with specified type and expiration."""
    to_encode = data.copy()
    to_encode.update({"token_type": token_type})
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(data: dict) -> str:
    """Create access token with 30 minutes expiration."""
    return create_token(data, "access", timedelta(minutes=30))


def create_refresh_token(data: dict) -> str:
    """Create refresh token with 30 days expiration."""
    return create_token(data, "refresh", timedelta(days=30))


def decode_token(token: str) -> dict:
    """Decode JWT token and return payload."""
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise InvalidTokenException()


def verify_token(token: HTTPAuthorizationCredentials | None, required_token_type: str) -> str:
    """Verify token and return email."""
    if token is None:
        raise InvalidTokenException()

    payload = decode_token(token.credentials)
    email: str = payload.get("sub")  # type: ignore
    token_type: str = payload.get("token_type")  # type: ignore

    if email is None:
        raise InvalidTokenException()

    if token_type != required_token_type:
        raise InvalidTokenException()

    return email


def verify_refresh_token(token_str: str) -> str:
    """Verify refresh token and return email."""
    token = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token_str)
    return verify_token(token, "refresh")
