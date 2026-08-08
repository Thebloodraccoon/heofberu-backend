"""Tests for the item write endpoints."""

import pytest


@pytest.mark.integration
class TestItemCrud:
    def test_player_cannot_create_item(self, client, player_token):
        response = client.post(
            "/items/",
            json={"name": "Custom Item", "item_type": "WEAPON", "rarity": "NONE"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    def test_gm_can_create_item(self, client, gm_token):
        response = client.post(
            "/items/",
            json={"name": "Longsword", "item_type": "WEAPON", "rarity": "NONE"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert response.json()["name"] == "Longsword"
        assert response.json()["item_type"] == "WEAPON"

    def test_create_duplicate_item_name_returns_400(self, client, gm_token, create_item):
        create_item(name="Longsword")
        response = client.post(
            "/items/",
            json={"name": "Longsword", "item_type": "WEAPON", "rarity": "NONE"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    def test_gm_can_update_item(self, client, gm_token, create_item):
        item = create_item(name="Old Item Name")

        response = client.patch(
            f"/items/{item.id}",
            json={"name": "New Item Name"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "New Item Name"

    def test_gm_cannot_delete_item(self, client, gm_token, create_item):
        item = create_item(name="Doomed Item")

        response = client.delete(f"/items/{item.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 403
        assert client.get(f"/items/{item.id}").status_code == 200

    def test_founder_can_delete_item(self, client, founder_token, create_item):
        item = create_item(name="Doomed Item")

        response = client.delete(f"/items/{item.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 204
        assert client.get(f"/items/{item.id}").status_code == 404
