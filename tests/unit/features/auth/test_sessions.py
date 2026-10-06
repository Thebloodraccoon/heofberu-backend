"""Unit tests for the Redis-backed session helpers (revocation timestamp, token claims, outage policy)."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import ServiceUnavailableError
from app.core.security.token import DecodedToken
from app.features.auth import sessions
from app.settings import settings


def decoded(jti: str = "j", issued_at_ms: int = 1000) -> DecodedToken:
    return DecodedToken("1", jti, datetime.now(timezone.utc) + timedelta(minutes=5), iat_ms=issued_at_ms)


class FakeRedis:
    """Minimal in-memory Redis: mget/set(nx)/delete."""

    def __init__(self):
        self.data: dict[str, str] = {}

    async def mget(self, *keys):
        return [self.data.get(key) for key in keys]

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.data:
            return None
        self.data[key] = str(value)
        return True

    async def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)


@pytest.fixture
def fake_redis(monkeypatch):
    redis = FakeRedis()

    @asynccontextmanager
    async def provider():
        yield redis

    monkeypatch.setattr(settings, "get_auth_redis", provider)
    return redis


@pytest.fixture
def broken_redis(monkeypatch):
    @asynccontextmanager
    async def provider():
        raise ConnectionError("secret-host:6379 refused")
        yield

    monkeypatch.setattr(settings, "get_auth_redis", provider)


@pytest.mark.unit
@pytest.mark.asyncio
class TestRevocation:
    async def test_not_revoked_by_default(self, fake_redis):
        assert await sessions.is_session_revoked(decoded("jti", 1000), 1) is False

    async def test_blacklisted_jti_is_revoked(self, fake_redis):
        assert await sessions.claim_token("jti-a", 60, reason="logout") is True

        assert await sessions.is_session_revoked(decoded("jti-a", 10**15), 1) is True

    async def test_tokens_issued_before_the_revocation_are_revoked(self, fake_redis, monkeypatch):
        monkeypatch.setattr(sessions, "now_ms", lambda: 5000)
        await sessions.revoke_user_sessions(7)

        assert await sessions.is_session_revoked(decoded("j", 4999), 7) is True
        assert await sessions.is_session_revoked(decoded("j", 5000), 7) is False
        assert await sessions.is_session_revoked(decoded("j", 5001), 7) is False

    async def test_revocation_is_per_user(self, fake_redis, monkeypatch):
        monkeypatch.setattr(sessions, "now_ms", lambda: 5000)
        await sessions.revoke_user_sessions(7)

        assert await sessions.is_session_revoked(decoded("j", 1), 8) is False

    async def test_revocation_key_is_outside_the_cache_prefix(self, fake_redis):
        await sessions.revoke_user_sessions(7)

        assert all(not key.startswith(f"{settings.CACHE_PREFIX}:") for key in fake_redis.data)


@pytest.mark.unit
@pytest.mark.asyncio
class TestClaims:
    async def test_second_claim_loses(self, fake_redis):
        assert await sessions.claim_token("j", 60, reason="r") is True
        assert await sessions.claim_token("j", 60, reason="r") is False

    async def test_release_allows_a_new_claim(self, fake_redis):
        await sessions.claim_token("j", 60, reason="r")
        await sessions.release_token("j")

        assert await sessions.claim_token("j", 60, reason="r") is True

    async def test_expired_ttl_never_claims(self, fake_redis):
        assert await sessions.claim_token("j", 0, reason="r") is False
        assert fake_redis.data == {}


@pytest.mark.unit
@pytest.mark.asyncio
class TestRedisOutageIsFailClosed:
    async def test_lookup(self, broken_redis):
        with pytest.raises(ServiceUnavailableError) as exc_info:
            await sessions.is_session_revoked(decoded("j", 1), 1)

        assert "secret-host" not in exc_info.value.message

    async def test_revoke(self, broken_redis):
        with pytest.raises(ServiceUnavailableError):
            await sessions.revoke_user_sessions(1)

    async def test_claim(self, broken_redis):
        with pytest.raises(ServiceUnavailableError):
            await sessions.claim_token("j", 60, reason="r")

    async def test_release_is_best_effort(self, broken_redis):
        await sessions.release_token("j")
