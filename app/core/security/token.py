"""
JWT creation, verification, and blacklisting utilities.

Implements access/refresh token creation with unique ``jti`` claims,
signature/expiry/type verification, and Redis-backed revocation of
individual tokens.

Redis access is async (``redis.asyncio`` via ``settings.get_redis``); all
other helpers stay synchronous since they are pure JWT operations.
"""

from datetime import datetime, timedelta, timezone
import logging
import uuid

from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError, jwt

from app.core.exceptions import InvalidTokenException, ServiceUnavailableError
from app.settings import settings

logger = logging.getLogger(__name__)

ACCESS_TOKEN_EXPIRES = timedelta(minutes=30)
REFRESH_TOKEN_EXPIRES = timedelta(days=30)
RESET_TOKEN_EXPIRES = timedelta(minutes=15)

_TOKEN_LIFETIMES = {"access": ACCESS_TOKEN_EXPIRES, "refresh": REFRESH_TOKEN_EXPIRES, "reset": RESET_TOKEN_EXPIRES}

_BLACKLIST_KEY_PREFIX = "token_blacklist:"


def create_token(data: dict, token_type: str, expires_delta: timedelta) -> str:
    """
    Create a JWT of the given type and expiration.

    Every token gets a unique ``jti`` (JWT ID) claim, independent of any
    other data in ``data`` — this is what lets a single token be targeted
    for revocation (see ``blacklist_token``) without blacklisting every
    token ever issued to the same user.

    ``iat`` (seconds) and ``iat_ms`` (milliseconds) record the issue time;
    values already present in ``data`` win, which lets tests mint tokens
    with a chosen issue time.
    """

    to_encode = data.copy()
    to_encode.update({"token_type": token_type, "jti": str(uuid.uuid4())})
    now = datetime.now(timezone.utc)
    to_encode.setdefault("iat", int(now.timestamp()))
    to_encode.setdefault("iat_ms", int(now.timestamp() * 1000))
    to_encode.update({"exp": now + expires_delta})

    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(data: dict) -> str:
    """Create access token with 30 minutes expiration."""

    return create_token(data, "access", ACCESS_TOKEN_EXPIRES)


def create_refresh_token(data: dict) -> str:
    """Create refresh token with 30 days expiration."""

    return create_token(data, "refresh", REFRESH_TOKEN_EXPIRES)


def create_reset_token(data: dict) -> str:
    """Create a short-lived (15 min) password-reset token."""

    return create_token(data, "reset", RESET_TOKEN_EXPIRES)


def decode_token(token: str) -> dict:
    """Decode JWT token and return payload."""

    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise InvalidTokenException()


class DecodedToken:
    """
    Parsed, validated token payload plus the fields callers actually need
    (subject, jti, remaining TTL, issue time) — replaces passing a bare
    ``str`` around once callers also need ``jti`` for blacklist checks/writes.

    ``subject`` is the raw ``sub`` claim: a user id string for current
    tokens, an email for tokens minted before ids were used.
    """

    def __init__(
        self,
        subject: str,
        jti: str,
        expires_at: datetime,
        token_type: str = "access",
        iat_ms: int | None = None,
    ):
        self.subject = subject
        self.jti = jti
        self.expires_at = expires_at
        self.token_type = token_type
        self._iat_ms = iat_ms

    @property
    def issued_at_ms(self) -> int:
        """
        Issue time in milliseconds.

        Uses the ``iat_ms`` claim; tokens minted before it existed fall back
        to ``exp`` minus the lifetime of their type (whole-second precision).
        """

        if self._iat_ms is not None:
            return self._iat_ms

        lifetime = _TOKEN_LIFETIMES.get(self.token_type, ACCESS_TOKEN_EXPIRES)
        return int((self.expires_at - lifetime).timestamp() * 1000)

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


def verify_reset_token(token_str: str) -> DecodedToken:
    """Verify a password-reset token string and return its parsed claims."""

    return _verify_token_str(token_str, "reset")


def _verify_token_str(token_str: str, required_token_type: str) -> DecodedToken:
    """Verify token data."""

    payload = decode_token(token_str)

    subject: str | None = payload.get("sub")
    token_type: str | None = payload.get("token_type")
    jti: str | None = payload.get("jti")
    exp: int | None = payload.get("exp")

    if subject is None or jti is None or exp is None:
        raise InvalidTokenException()

    if token_type != required_token_type:
        raise InvalidTokenException()

    claimed_iat_ms = payload.get("iat_ms")
    return DecodedToken(
        subject=subject,
        jti=jti,
        expires_at=datetime.fromtimestamp(exp, tz=timezone.utc),
        token_type=token_type,
        iat_ms=claimed_iat_ms if isinstance(claimed_iat_ms, int) else None,
    )


def blacklist_key(jti: str) -> str:
    """Redis key under which a revoked or single-use token ``jti`` is stored."""

    return f"{_BLACKLIST_KEY_PREFIX}{jti}"


async def blacklist_token(jti: str, ttl_seconds: int, *, reason: str = "revoked") -> None:
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

    try:
        async with settings.get_redis() as redis:
            await redis.set(blacklist_key(jti), reason, ex=ttl_seconds)
    except Exception as exc:
        logger.error("Token blacklist write failed: %s", exc)
        raise ServiceUnavailableError("Authentication service temporarily unavailable") from exc


async def is_token_blacklisted(jti: str) -> bool:
    """
    Return whether ``jti`` has been revoked and hasn't expired yet.

    Fails closed: if Redis cannot answer, the request gets a 503 rather than
    letting a possibly revoked token through (or an opaque 500).
    """

    try:
        async with settings.get_redis() as redis:
            return await redis.exists(blacklist_key(jti)) > 0
    except Exception as exc:
        logger.error("Token blacklist lookup failed: %s", exc)
        raise ServiceUnavailableError("Authentication service temporarily unavailable") from exc
