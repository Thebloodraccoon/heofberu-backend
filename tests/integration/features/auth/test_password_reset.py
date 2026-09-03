"""Tests for the password-reset flow: forgot-password and reset-password."""

import pytest

from app.core.security.token import (
    create_reset_token,
    is_token_blacklisted,
    verify_reset_token,
)
from app.core.security.password import verify_password_async
from app.features.users.repository import UserRepository


@pytest.mark.integration
@pytest.mark.asyncio
class TestForgotPassword:
    async def test_forgot_password_for_existing_user_returns_neutral_response(self, client, create_user):
        await create_user(email="reset1@example.com", password="password123")
        response = await client.post("/auth/forgot-password", json={"email": "reset1@example.com"})

        assert response.status_code == 200
        assert "reset link has been sent" in response.json()["detail"]

    async def test_forgot_password_for_unknown_user_returns_same_response(self, client):
        """The response must be identical to the existing-user case to prevent enumeration."""
        response = await client.post("/auth/forgot-password", json={"email": "nobody@example.com"})

        assert response.status_code == 200
        assert "reset link has been sent" in response.json()["detail"]

    async def test_forgot_password_rejects_invalid_email(self, client):
        response = await client.post("/auth/forgot-password", json={"email": "not-an-email"})

        assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
class TestResetPassword:
    async def test_reset_password_success_and_blacklists_token(
        self, client, db_session, redis_client, create_user
    ):
        user = await create_user(email="reset2@example.com", password="old-password-123")
        reset_token = create_reset_token(data={"sub": user.email})
        decoded = verify_reset_token(reset_token)

        response = await client.post(
            "/auth/reset-password",
            json={
                "token": reset_token,
                "new_password": "new-password-456",
                "confirm_password": "new-password-456",
            },
        )

        assert response.status_code == 200
        assert response.json()["detail"] == "Password has been reset. You can now log in."

        repo = UserRepository(db_session)
        updated = await repo.get_by_email(user.email)
        assert await verify_password_async("new-password-456", updated.hashed_password)
        assert await is_token_blacklisted(decoded.jti) is True

    async def test_reset_used_token_is_rejected(self, client, db_session, redis_client, create_user):
        """A reset token must be single-use — replaying it after use must fail."""
        user = await create_user(email="reset3@example.com", password="old-password-123")
        reset_token = create_reset_token(data={"sub": user.email})

        first = await client.post(
            "/auth/reset-password",
            json={
                "token": reset_token,
                "new_password": "new-password-456",
                "confirm_password": "new-password-456",
            },
        )
        assert first.status_code == 200

        second = await client.post(
            "/auth/reset-password",
            json={
                "token": reset_token,
                "new_password": "another-password-789",
                "confirm_password": "another-password-789",
            },
        )

        assert second.status_code == 400

    async def test_reset_with_invalid_token_returns_400(self, client):
        response = await client.post(
            "/auth/reset-password",
            json={
                "token": "not-a-real-token",
                "new_password": "new-password-456",
                "confirm_password": "new-password-456",
            },
        )

        assert response.status_code == 400

    async def test_reset_rejects_weak_password(self, client, create_user):
        user = await create_user(email="reset4@example.com", password="password123")
        reset_token = create_reset_token(data={"sub": user.email})

        response = await client.post(
            "/auth/reset-password",
            json={
                "token": reset_token,
                "new_password": "short",
                "confirm_password": "short",
            },
        )

        assert response.status_code == 400

    async def test_reset_rejects_mismatched_passwords(self, client, create_user):
        user = await create_user(email="reset5@example.com", password="password123")
        reset_token = create_reset_token(data={"sub": user.email})

        response = await client.post(
            "/auth/reset-password",
            json={
                "token": reset_token,
                "new_password": "new-password-456",
                "confirm_password": "different-456",
            },
        )

        assert response.status_code == 400

    async def test_new_password_works_for_login(self, client, create_user):
        """After a reset, the new password authenticates and the old one does not."""
        user = await create_user(email="reset6@example.com", password="old-password-123")
        reset_token = create_reset_token(data={"sub": user.email})

        await client.post(
            "/auth/reset-password",
            json={
                "token": reset_token,
                "new_password": "new-password-456",
                "confirm_password": "new-password-456",
            },
        )

        old_password_login = await client.post(
            "/auth/login", json={"email": user.email, "password": "old-password-123"}
        )
        assert old_password_login.status_code == 401

        new_password_login = await client.post(
            "/auth/login", json={"email": user.email, "password": "new-password-456"}
        )
        assert new_password_login.status_code == 200
        assert "access_token" in new_password_login.json()
