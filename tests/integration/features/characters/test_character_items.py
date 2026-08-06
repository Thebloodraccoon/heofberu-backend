"""Tests for character item endpoints: inventory management."""

import pytest


@pytest.mark.integration
class TestCharacterItems:
    def test_add_and_list_item(self, client, player, player_token, create_class, create_character, create_item):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)
        item = create_item(name="Longsword")

        add_response = client.post(
            f"/characters/{character.id}/items",
            json={"item_id": item.id, "quantity": 2, "is_equipped": True, "notes": "Primary"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert add_response.status_code == 201
        assert add_response.json()["item_id"] == item.id
        assert add_response.json()["quantity"] == 2
        assert add_response.json()["is_equipped"] is True
        assert add_response.json()["notes"] == "Primary"

        list_response = client.get(
            f"/characters/{character.id}/items",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert list_response.status_code == 200
        assert [item_entry["item_id"] for item_entry in list_response.json()] == [item.id]

    def test_add_missing_item_returns_404(self, client, player, player_token, create_class, create_character):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)

        response = client.post(
            f"/characters/{character.id}/items",
            json={"item_id": 999999},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 404

    def test_update_item_stack(self, client, player, player_token, create_class, create_character, create_item):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)
        item = create_item(name="Longsword")
        add_response = client.post(
            f"/characters/{character.id}/items",
            json={"item_id": item.id, "quantity": 1},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        character_item_id = add_response.json()["id"]

        response = client.patch(
            f"/characters/{character.id}/items/{character_item_id}",
            json={"quantity": 3, "is_attuned": True},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["quantity"] == 3
        assert response.json()["is_attuned"] is True
        assert response.json()["is_equipped"] is False

    def test_remove_item(self, client, player, player_token, create_class, create_character, create_item):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)
        item = create_item(name="Longsword")
        add_response = client.post(
            f"/characters/{character.id}/items",
            json={"item_id": item.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        character_item_id = add_response.json()["id"]

        response = client.delete(
            f"/characters/{character.id}/items/{character_item_id}",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 204
        assert (
            client.get(
                f"/characters/{character.id}/items",
                headers={"Authorization": f"Bearer {player_token}"},
            ).json()
            == []
        )

    def test_same_item_can_be_added_as_multiple_stacks(
        self, client, player, player_token, create_class, create_character, create_item
    ):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)
        item = create_item(name="Longsword")

        first = client.post(
            f"/characters/{character.id}/items",
            json={"item_id": item.id, "is_equipped": True},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        second = client.post(
            f"/characters/{character.id}/items",
            json={"item_id": item.id, "is_equipped": False},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert first.status_code == 201
        assert second.status_code == 201
        list_response = client.get(
            f"/characters/{character.id}/items",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert len(list_response.json()) == 2

    def test_player_cannot_add_item_to_other_players_character(
        self, client, player_token, create_user, create_class, create_character, create_item
    ):
        character_class = create_class(name="Fighter")
        other = create_user(username="other", email="other@example.com")
        character = create_character(owner_id=other.id, class_id=character_class.id)
        item = create_item(name="Longsword")

        response = client.post(
            f"/characters/{character.id}/items",
            json={"item_id": item.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
