"""Tests for the user management endpoints (GM/founder) and the personal cabinet."""

import pytest

from app.settings import settings


@pytest.mark.integration
@pytest.mark.asyncio
class TestUserCrud:
    async def test_player_cannot_create_user(self, client, player_token):
        response = await client.post(
            "/users/",
            json={"username": "hacker", "email": "hacker@example.com", "password": "password123"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_create_user(self, client, gm_token):
        response = await client.post(
            "/users/",
            json={"username": "newbie", "email": "newbie@example.com", "password": "password123"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["username"] == "newbie"
        assert body["role"] == "player"
        assert "hashed_password" not in body

    async def test_gm_cannot_create_gm_user(self, client, gm_token):
        response = await client.post(
            "/users/",
            json={"username": "gm2", "email": "gm2@example.com", "password": "password123", "role": "gm"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 403

    async def test_founder_can_create_gm_user(self, client, founder_token):
        response = await client.post(
            "/users/",
            json={"username": "gm2", "email": "gm2@example.com", "password": "password123", "role": "gm"},
            headers={"Authorization": f"Bearer {founder_token}"},
        )

        assert response.status_code == 201
        assert response.json()["role"] == "gm"

    async def test_create_user_duplicate_email_returns_400(self, client, gm_token, create_user):
        await create_user(email="taken@example.com")
        response = await client.post(
            "/users/",
            json={"username": "other", "email": "taken@example.com", "password": "password123"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_gm_can_update_user(self, client, gm_token, create_user):
        user = await create_user(username="oldname", email="oldname@example.com")

        response = await client.put(
            f"/users/{user.id}",
            json={"username": "newname"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["username"] == "newname"

    async def test_gm_cannot_update_role(self, client, gm_token, create_user):
        user = await create_user(username="victim", email="victim@example.com")

        response = await client.put(
            f"/users/{user.id}",
            json={"role": "gm"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 403

    async def test_founder_can_update_role(self, client, founder_token, create_user):
        user = await create_user(username="victim2", email="victim2@example.com")

        response = await client.put(
            f"/users/{user.id}",
            json={"role": "gm"},
            headers={"Authorization": f"Bearer {founder_token}"},
        )

        assert response.status_code == 200
        assert response.json()["role"] == "gm"

    async def test_founder_can_delete_user(self, client, founder_token, create_user):
        user = await create_user(username="doomed", email="doomed@example.com")

        response = await client.delete(f"/users/{user.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 204
        assert (
            await client.get(f"/users/{user.id}", headers={"Authorization": f"Bearer {founder_token}"})
        ).status_code == 404

    async def test_gm_cannot_delete_user(self, client, gm_token, create_user):
        user = await create_user(username="protected", email="protected@example.com")

        response = await client.delete(f"/users/{user.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 403

    async def test_cannot_delete_self(self, client, founder_token, founder):
        response = await client.delete(f"/users/{founder.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 403

    async def test_cannot_delete_default_admin(self, client, founder_token, create_user):
        default_admin = await create_user(username="tuttamus", email=settings.ADMIN_LOGIN)

        response = await client.delete(f"/users/{default_admin.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestPersonalCabinet:
    async def test_user_can_update_own_profile(self, client, player_token, player):
        response = await client.put(
            "/users/me",
            json={"bio": "Люблю драконов", "location": "Москва", "contact": "@telegram"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["bio"] == "Люблю драконов"
        assert body["location"] == "Москва"
        assert body["contact"] == "@telegram"
        assert body["role"] == "player"

    async def test_user_can_update_username_and_email(self, client, player_token):
        response = await client.put(
            "/users/me",
            json={"username": "renamed", "email": "renamed@example.com"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["username"] == "renamed"
        assert body["email"] == "renamed@example.com"

    async def test_profile_update_rejects_empty_payload(self, client, player_token):
        response = await client.put("/users/me", json={}, headers={"Authorization": f"Bearer {player_token}"})

        assert response.status_code == 422

    async def test_profile_update_cannot_change_role(self, client, player_token):
        response = await client.put(
            "/users/me",
            json={"role": "gm", "bio": "независимо"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 422

    async def test_default_admin_can_update_own_profile(self, client, create_user, login_as):
        admin = await create_user(username="tuttamus", email=settings.ADMIN_LOGIN)
        token = await login_as(admin)

        response = await client.put(
            "/users/me",
            json={"bio": "Основатель мира"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["bio"] == "Основатель мира"
