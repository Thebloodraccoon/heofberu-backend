"""Tests for character item endpoints: reads are GM/owner, writes are GM-only."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterItems:
    async def test_add_and_list_item(
        self, client, gm_token, player, player_token, create_class, create_character, create_item
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        item = await create_item(name="Longsword")

        add_response = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": item.id, "quantity": 2, "is_equipped": True, "notes": "Primary"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert add_response.status_code == 201
        assert add_response.json()["item_id"] == item.id
        assert add_response.json()["quantity"] == 2
        assert add_response.json()["is_equipped"] is True
        assert add_response.json()["notes"] == "Primary"

        list_response = await client.get(
            f"/characters/{character.id}/gm-panel/items",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert list_response.status_code == 200
        assert [item_entry["item_id"] for item_entry in list_response.json()] == [item.id]

    async def test_add_missing_item_returns_404(self, client, gm_token, player, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": 999999},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404

    async def test_update_item_stack(
        self, client, gm_token, player, player_token, create_class, create_character, create_item
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        item = await create_item(name="Longsword")
        add_response = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": item.id, "quantity": 1},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        character_item_id = add_response.json()["id"]

        response = await client.patch(
            f"/characters/{character.id}/gm-panel/items",
            params={"item_id": character_item_id},
            json={"quantity": 3, "is_attuned": True},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["quantity"] == 3
        assert response.json()["is_attuned"] is True
        assert response.json()["is_equipped"] is False

    async def test_remove_item(
        self, client, gm_token, player, player_token, create_class, create_character, create_item
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        item = await create_item(name="Longsword")
        add_response = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": item.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        character_item_id = add_response.json()["id"]

        response = await client.delete(
            f"/characters/{character.id}/gm-panel/items",
            params={"item_id": character_item_id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 204
        assert (
            await client.get(
                f"/characters/{character.id}/gm-panel/items",
                headers={"Authorization": f"Bearer {player_token}"},
            )
        ).json() == []

    async def test_same_item_can_be_added_as_multiple_stacks(
        self, client, gm_token, player, player_token, create_class, create_character, create_item
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        item = await create_item(name="Longsword")

        first = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": item.id, "is_equipped": True},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        second = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": item.id, "is_equipped": False},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert first.status_code == 201
        assert second.status_code == 201
        list_response = await client.get(
            f"/characters/{character.id}/gm-panel/items",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert len(list_response.json()) == 2

    async def test_player_cannot_manage_inventory_even_own_character(
        self, client, player, player_token, create_class, create_character, create_item
    ):
        """Item writes are GM-panel operations — even the owner gets a 403."""

        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        item = await create_item(name="Longsword")

        add_response = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": item.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert add_response.status_code == 403

    async def test_player_cannot_remove_item_stack(
        self, client, gm_token, player, player_token, create_class, create_character, create_item
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        item = await create_item(name="Longsword")
        add_response = await client.post(
            f"/characters/{character.id}/gm-panel/items",
            json={"item_id": item.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        character_item_id = add_response.json()["id"]

        response = await client.delete(
            f"/characters/{character.id}/gm-panel/items",
            params={"item_id": character_item_id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
