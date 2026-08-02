from datetime import datetime, timedelta, timezone
import uuid

from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError, jwt

from app.core.exceptions import InvalidTokenException
from app.settings import settings
from app.settings.local import get_redis

ACCESS_TOKEN_EXPIRES = timedelta(minutes=30)
REFRESH_TOKEN_EXPIRES = timedelta(days=30)

_BLACKLIST_KEY_PREFIX = "token_blacklist:"


def create_token(data: dict, token_type: str, expires_delta: timedelta) -> str:
    """
    Create a JWT of the given type and expiration.

    Every token gets a unique ``jti`` (JWT ID) claim, independent of any
    other data in ``data`` — this is what lets a single token be targeted
    for revocation (see ``blacklist_token``) without blacklisting every
    token ever issued to the same user.
    """

    to_encode = data.copy()
    to_encode.update({"token_type": token_type, "jti": str(uuid.uuid4())})
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(data: dict) -> str:
    """Create access token with 30 minutes expiration."""

    return create_token(data, "access", ACCESS_TOKEN_EXPIRES)


def create_refresh_token(data: dict) -> str:
    """Create refresh token with 30 days expiration."""

    return create_token(data, "refresh", REFRESH_TOKEN_EXPIRES)


def decode_token(token: str) -> dict:
    """Decode JWT token and return payload."""

    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise InvalidTokenException()


class DecodedToken:
    """
    Parsed, validated token payload plus the fields callers actually need
    (email, jti, remaining TTL) — replaces passing a bare ``str`` (email)
    around once callers also need ``jti`` for blacklist checks/writes.
    """

    def __init__(self, email: str, jti: str, expires_at: datetime):
        self.email = email
        self.jti = jti
        self.expires_at = expires_at

    @property
    def remaining_seconds(self) -> int:
        """
        Seconds until this token's own expiration, floored at 0.

        Used as the blacklist entry's TTL: once the token would have
        expired naturally anyway, there's no need to keep the blacklist
        entry around — Redis expires it for us at the same moment.
        """

        remaining_seconds = self.expires_at - datetime.now(timezone.utc)
        return max(int(remaining_seconds.total_seconds()), 0)


def verify_token(token: HTTPAuthorizationCredentials | None, required_token_type: str) -> DecodedToken:
    """
    Verify a bearer token's signature, expiration, and type, returning its
    parsed claims.

    Does not check the blacklist itself — callers that care about
    revocation (``get_current_user``, refresh) do that explicitly via
    ``is_token_blacklisted``, keeping token verification and revocation
    as separate, composable steps.
    """

    if token is None:
        raise InvalidTokenException()

    return _verify_token_str(token.credentials, required_token_type)


def verify_refresh_token(token_str: str) -> DecodedToken:
    """Verify refresh token string and return its parsed claims."""

    return _verify_token_str(token_str, "refresh")


def _verify_token_str(token_str: str, required_token_type: str) -> DecodedToken:
    """Verify token data."""

    payload = decode_token(token_str)

    email: str | None = payload.get("sub")
    token_type: str | None = payload.get("token_type")
    jti: str | None = payload.get("jti")
    exp: int | None = payload.get("exp")

    if email is None or jti is None or exp is None:
        raise InvalidTokenException()

    if token_type != required_token_type:
        raise InvalidTokenException()

    return DecodedToken(email=email, jti=jti, expires_at=datetime.fromtimestamp(exp, tz=timezone.utc))


def _blacklist_key(jti: str) -> str:
    return f"{_BLACKLIST_KEY_PREFIX}{jti}"


def blacklist_token(jti: str, ttl_seconds: int, *, reason: str = "revoked") -> None:
    """
    Mark a token's ``jti`` as revoked for ``ttl_seconds``.

    ``ttl_seconds`` should be the token's own remaining lifetime (see
    ``DecodedToken.remaining_seconds``) — once the token would have
    expired naturally, the blacklist entry is redundant, and Redis's
    ``EX`` drops it automatically instead of it lingering forever. A
    ``ttl_seconds <= 0`` is a no-op: an already-expired token needs no
    blacklist entry, since ``decode_token`` will reject it as expired
    regardless.

    ``reason`` is stored as the value purely for operator debugging
    (e.g. inspecting a key in ``redis-cli`` mid-incident); the blacklist
    check itself only cares whether the key exists, not its value.
    """
    if ttl_seconds <= 0:
        return

    with get_redis() as redis:
        redis.set(_blacklist_key(jti), reason, ex=ttl_seconds)


def is_token_blacklisted(jti: str) -> bool:
    """Return whether ``jti`` has been revoked and hasn't expired yet."""
    with get_redis() as redis:
        return redis.exists(_blacklist_key(jti)) > 0
