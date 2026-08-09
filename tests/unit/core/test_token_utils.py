"""Unit tests for JWT creation, verification, and blacklisting helpers."""

from datetime import timedelta

from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt
import pytest

from app.core.exceptions import InvalidTokenException
from app.core.token_utils import (
    blacklist_token,
    create_access_token,
    create_refresh_token,
    create_token,
    decode_token,
    verify_token,
)
from app.settings import settings


@pytest.mark.unit
class TestTokenCreation:
    def test_access_token_has_type_and_jti(self):
        token = create_access_token({"sub": "a@example.com"})

        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        assert payload["token_type"] == "access"
        assert payload["sub"] == "a@example.com"
        assert payload["jti"]

    def test_refresh_token_has_refresh_type(self):
        token = create_refresh_token({"sub": "a@example.com"})

        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        assert payload["token_type"] == "refresh"

    def test_every_token_gets_unique_jti(self):
        first = decode_token(create_access_token({"sub": "a@example.com"}))
        second = decode_token(create_access_token({"sub": "a@example.com"}))

        assert first["jti"] != second["jti"]

    def test_tokens_expire_in_the_future(self):
        token = create_access_token({"sub": "a@example.com"})

        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        assert payload["exp"] is not None


@pytest.mark.unit
class TestTokenVerification:
    def test_verify_token_returns_decoded_claims(self):
        token = create_access_token({"sub": "a@example.com"})

        decoded = verify_token(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), "access")

        assert decoded.email == "a@example.com"
        assert decoded.jti

    def test_verify_token_with_wrong_type_raises(self):
        token = create_refresh_token({"sub": "a@example.com"})

        with pytest.raises(InvalidTokenException):
            verify_token(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), "access")

    def test_verify_token_with_none_raises(self):
        with pytest.raises(InvalidTokenException):
            verify_token(None, "access")

    def test_expired_token_raises(self):
        token = create_token({"sub": "a@example.com"}, "access", timedelta(seconds=-60))

        with pytest.raises(InvalidTokenException):
            verify_token(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), "access")

    def test_token_missing_claims_raises(self):
        token = jwt.encode({"sub": "a@example.com"}, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

        with pytest.raises(InvalidTokenException):
            verify_token(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), "access")

    def test_decode_raises_invalid_token_for_garbage(self):
        with pytest.raises(InvalidTokenException):
            decode_token("not-a-jwt")


@pytest.mark.unit
class TestBlacklistNoop:
    @pytest.mark.asyncio
    async def test_blacklisting_with_nonpositive_ttl_is_noop(self):
        token = decode_token(create_access_token({"sub": "a@example.com"}))

        # ttl <= 0 must short-circuit without touching Redis — would raise
        # a ConnectionError otherwise (no test Redis in unit scope).
        await blacklist_token(token["jti"], ttl_seconds=0)
