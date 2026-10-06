"""
Server-side session state kept in Redis: per-user revocation and single-use token claims.

* **Revocation timestamp** — ``revoke_user_sessions(user_id)`` makes every
  token issued before "now" invalid for that user (used after a password
  reset). Tokens carry a millisecond ``iat_ms`` claim (see
  ``DecodedToken.issued_at_ms``), so no DB column is needed.
  The key expires after the longest token lifetime, when it can no longer matter.
* **Single-use claims** — ``claim_token`` is an atomic ``SET NX`` on the
  token's blacklist key: the first caller wins, concurrent/replayed callers
  lose. Refresh rotation and password-reset links rely on it.

Redis being unreachable is fail-closed (503), matching the JWT blacklist.
"""

import logging
import time

from app.core.exceptions import ServiceUnavailableError
from app.core.security.token import REFRESH_TOKEN_EXPIRES, DecodedToken, blacklist_key
from app.settings import settings

logger = logging.getLogger(__name__)

_REVOKED_AFTER_PREFIX = "auth_revoked_after"
_UNAVAILABLE_MESSAGE = "Authentication service temporarily unavailable"


def _revoked_after_key(user_id: int) -> str:
    return f"{_REVOKED_AFTER_PREFIX}:{settings.CACHE_PREFIX}:{user_id}"


def now_ms() -> int:
    """Current time in milliseconds, the unit of ``iat_ms`` and of the revocation timestamp."""

    return int(time.time() * 1000)


async def is_session_revoked(decoded: DecodedToken, user_id: int) -> bool:
    """
    Whether the token is blacklisted or was issued before the user's revocation timestamp.

    One ``MGET`` for both checks, so authentication costs a single extra Redis round trip.
    """

    try:
        async with settings.get_auth_redis() as redis:
            blacklisted, revoked_after = await redis.mget(blacklist_key(decoded.jti), _revoked_after_key(user_id))
    except Exception as exc:
        logger.error("Session revocation lookup failed: %s", exc)
        raise ServiceUnavailableError(_UNAVAILABLE_MESSAGE) from exc

    if blacklisted is not None:
        return True

    return revoked_after is not None and decoded.issued_at_ms < int(revoked_after)


async def revoke_user_sessions(user_id: int) -> None:
    """Invalidate every access/refresh token issued to ``user_id`` before this moment."""

    try:
        async with settings.get_auth_redis() as redis:
            await redis.set(
                _revoked_after_key(user_id),
                now_ms(),
                ex=int(REFRESH_TOKEN_EXPIRES.total_seconds()),
            )
    except Exception as exc:
        logger.error("Session revocation write failed: %s", exc)
        raise ServiceUnavailableError(_UNAVAILABLE_MESSAGE) from exc


async def claim_token(jti: str, ttl_seconds: int, *, reason: str) -> bool:
    """
    Atomically mark a token as used; ``True`` only for the first caller.

    The marker is the regular blacklist entry, so a claimed token is also
    rejected everywhere the blacklist is consulted. An already-expired
    token (``ttl_seconds <= 0``) can never be claimed.
    """

    if ttl_seconds <= 0:
        return False

    try:
        async with settings.get_auth_redis() as redis:
            return bool(await redis.set(blacklist_key(jti), reason, ex=ttl_seconds, nx=True))
    except Exception as exc:
        logger.error("Token claim failed: %s", exc)
        raise ServiceUnavailableError(_UNAVAILABLE_MESSAGE) from exc


async def release_token(jti: str) -> None:
    """Undo :func:`claim_token` after the guarded operation failed, so the token can be retried (best-effort)."""

    try:
        async with settings.get_auth_redis() as redis:
            await redis.delete(blacklist_key(jti))
    except Exception:
        logger.warning("Could not release claimed token", exc_info=True)
