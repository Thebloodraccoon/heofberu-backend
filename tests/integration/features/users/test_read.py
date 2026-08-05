"""Tests for the user read endpoints."""

import pytest


@pytest.mark.integration
class TestUserRead:
    def test_list_users_requires_auth(self, client):
        assert client.get("/users/").status_code == 401

    def test_player_cannot_list_users(self, client, player_token):
        response = client.get("/users/", headers={"Authorization": f"Bearer {player_token}"})

        assert response.status_code == 403

    def test_list_users_paginated_with_filters(self, client, gm_token, create_user):
        create_user(username="alpha", email="alpha@example.com")
        create_user(username="gmuser", email="gmuser@example.com", role="GM")

        all_response = client.get("/users/", headers={"Authorization": f"Bearer {gm_token}"})
        assert all_response.status_code == 200
        assert all_response.json()["total"] >= 2

        gm_response = client.get("/users/?role=gm", headers={"Authorization": f"Bearer {gm_token}"})
        assert gm_response.status_code == 200
        assert all(item["role"] == "gm" for item in gm_response.json()["items"])

        search_response = client.get("/users/?search=alpha", headers={"Authorization": f"Bearer {gm_token}"})
        assert search_response.status_code == 200
        assert [item["username"] for item in search_response.json()["items"]] == ["alpha"]

    def test_get_user_by_id(self, client, gm_token, create_user):
        user = create_user(username="target", email="target@example.com")

        response = client.get(f"/users/{user.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 200
        assert response.json()["username"] == "target"

    def test_get_user_404(self, client, gm_token):
        assert client.get("/users/999999", headers={"Authorization": f"Bearer {gm_token}"}).status_code == 404
