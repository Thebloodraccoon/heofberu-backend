"""Tests for the auth endpoints: register, login, refresh, logout."""

import pytest

from app.core.token_utils import decode_token, is_token_blacklisted


@pytest.mark.integration
@pytest.mark.asyncio
class TestRegister:
    async def test_register_creates_player_and_returns_access_token(self, client, db_session):
        response = await client.post(
            "/auth/register",
            json={"username": "newbie", "email": "newbie@example.com", "password": "password123"},
        )

        assert response.status_code == 201
        body = response.json()
        assert "access_token" in body
        assert decode_token(body["access_token"])["sub"] == "newbie@example.com"

    async def test_register_sets_refresh_cookie(self, client):
        response = await client.post(
            "/auth/register",
            json={"username": "newbie2", "email": "newbie2@example.com", "password": "password123"},
        )

        assert response.status_code == 201
        assert "refresh_token" in response.cookies

    async def test_register_creates_player_role(self, client):
        """Self-registered accounts are always PLAYER — a GM-only endpoint rejects their token."""
        response = await client.post(
            "/auth/register",
            json={"username": "newbie3", "email": "newbie3@example.com", "password": "password123"},
        )
        assert response.status_code == 201
        access_token = response.json()["access_token"]

        gm_only_response = await client.get("/users", headers={"Authorization": f"Bearer {access_token}"})

        assert gm_only_response.status_code == 403

    async def test_register_rejects_duplicate_email(self, client, create_user):
        user = await create_user(email="dup@example.com")
        response = await client.post(
            "/auth/register",
            json={"username": "someone", "email": user.email, "password": "password123"},
        )

        assert response.status_code == 400

    async def test_register_rejects_invalid_email(self, client):
        response = await client.post(
            "/auth/register",
            json={"username": "badmail", "email": "not-an-email", "password": "password123"},
        )

        assert response.status_code == 400

    async def test_register_rejects_short_password(self, client):
        response = await client.post(
            "/auth/register",
            json={"username": "shortpw", "email": "shortpw@example.com", "password": "short"},
        )

        assert response.status_code == 400

    async def test_register_rejects_invalid_username(self, client):
        response = await client.post(
            "/auth/register",
            json={"username": "ab", "email": "ab@example.com", "password": "password123"},
        )

        assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
class TestLogin:
    async def test_login_success_returns_access_token(self, client, create_user, db_session):
        await create_user(email="login@example.com", password="password123")
        response = await client.post("/auth/login", json={"email": "login@example.com", "password": "password123"})

        assert response.status_code == 200
        assert "access_token" in response.json()
        assert "refresh_token" in response.cookies

    async def test_login_wrong_password_returns_401(self, client, create_user):
        await create_user(email="login2@example.com", password="password123")
        response = await client.post("/auth/login", json={"email": "login2@example.com", "password": "wrongpass"})

        assert response.status_code == 401

    async def test_login_unknown_email_returns_401(self, client):
        response = await client.post("/auth/login", json={"email": "nobody@example.com", "password": "password123"})

        assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
class TestRefresh:
    async def test_refresh_exchanges_cookie_for_access_token(self, client, create_user, login_as):
        await create_user(email="refresh@example.com", password="password123")
        await client.post("/auth/login", json={"email": "refresh@example.com", "password": "password123"})

        response = await client.post("/auth/refresh")

        assert response.status_code == 200
        assert "access_token" in response.json()

    async def test_refresh_without_cookie_returns_401(self, client):
        response = await client.post("/auth/refresh")

        assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
class TestLogout:
    async def test_logout_blacklists_access_token(self, client, redis_client, create_user, login_as):
        user = await create_user(email="logout@example.com", password="password123")
        access_token = await login_as(user)

        logout_response = await client.post("/auth/logout", headers={"Authorization": f"Bearer {access_token}"})

        assert logout_response.status_code == 200
        assert logout_response.json()["detail"] == "Successful logout"

        decoded = decode_token(access_token)
        assert await is_token_blacklisted(decoded["jti"]) is True

    async def test_blacklisted_token_is_rejected(self, client, redis_client, create_user, login_as):
        user = await create_user(email="logout2@example.com", password="password123")
        access_token = await login_as(user)
        await client.post("/auth/logout", headers={"Authorization": f"Bearer {access_token}"})

        response = await client.get("/characters", headers={"Authorization": f"Bearer {access_token}"})

        assert response.status_code == 401

    async def test_logout_without_token_returns_401(self, client, redis_client):
        response = await client.post("/auth/logout")

        assert response.status_code == 401
