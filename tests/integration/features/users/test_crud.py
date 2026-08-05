"""Tests for the GM-only user management write endpoints."""

import pytest

from app.settings import settings


@pytest.mark.integration
class TestUserCrud:
    def test_player_cannot_create_user(self, client, player_token):
        response = client.post(
            "/users/",
            json={"username": "hacker", "email": "hacker@example.com", "password": "password123"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    def test_gm_can_create_user(self, client, gm_token):
        response = client.post(
            "/users/",
            json={"username": "newbie", "email": "newbie@example.com", "password": "password123"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["username"] == "newbie"
        assert body["role"] == "player"
        assert "hashed_password" not in body

    def test_gm_can_create_gm_user(self, client, gm_token):
        response = client.post(
            "/users/",
            json={"username": "gm2", "email": "gm2@example.com", "password": "password123", "role": "gm"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert response.json()["role"] == "gm"

    def test_create_user_duplicate_email_returns_400(self, client, gm_token, create_user):
        create_user(email="taken@example.com")
        response = client.post(
            "/users/",
            json={"username": "other", "email": "taken@example.com", "password": "password123"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    def test_gm_can_update_user(self, client, gm_token, create_user):
        user = create_user(username="oldname", email="oldname@example.com")

        response = client.put(
            f"/users/{user.id}",
            json={"username": "newname"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["username"] == "newname"

    def test_gm_can_delete_user(self, client, gm_token, create_user):
        user = create_user(username="doomed", email="doomed@example.com")

        response = client.delete(f"/users/{user.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 204
        assert client.get(f"/users/{user.id}", headers={"Authorization": f"Bearer {gm_token}"}).status_code == 404

    def test_cannot_delete_self(self, client, gm_token, gm):
        response = client.delete(f"/users/{gm.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 403

    def test_cannot_delete_default_admin(self, client, gm_token, create_user):
        default_admin = create_user(username="tuttamus", email=settings.ADMIN_LOGIN)

        response = client.delete(f"/users/{default_admin.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 403
