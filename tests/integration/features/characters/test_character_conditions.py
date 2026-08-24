"""Tests for character condition endpoints: active condition management."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterConditions:
    async def test_add_and_list_condition(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        add_response = await client.post(
            "/characters/conditions",
            params={"character_id": character.id},
            json={"condition": "POISONED", "source": "Giant Spider bite"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert add_response.status_code == 201
        assert add_response.json()["condition"] == "POISONED"
        assert add_response.json()["source"] == "Giant Spider bite"

        list_response = await client.get(
            "/characters/conditions",
            params={"character_id": character.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert list_response.status_code == 200
        assert [item["condition"] for item in list_response.json()] == ["POISONED"]

    async def test_add_exhaustion_without_level_returns_422(
        self, client, player, player_token, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.post(
            "/characters/conditions",
            params={"character_id": character.id},
            json={"condition": "EXHAUSTION"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 422

    async def test_add_exhaustion_with_level(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.post(
            "/characters/conditions",
            params={"character_id": character.id},
            json={"condition": "EXHAUSTION", "exhaustion_level": 2},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 201
        assert response.json()["exhaustion_level"] == 2

    async def test_add_level_to_non_exhaustion_condition_returns_422(
        self, client, player, player_token, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.post(
            "/characters/conditions",
            params={"character_id": character.id},
            json={"condition": "POISONED", "exhaustion_level": 2},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 422

    async def test_add_unknown_condition_returns_422(
        self, client, player, player_token, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.post(
            "/characters/conditions",
            params={"character_id": character.id},
            json={"condition": "SNOOZING"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 422

    async def test_duplicate_condition_returns_409(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        await client.post(
            "/characters/conditions",
            params={"character_id": character.id},
            json={"condition": "POISONED"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        response = await client.post(
            "/characters/conditions",
            params={"character_id": character.id},
            json={"condition": "POISONED"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 409

    async def test_update_exhaustion_level(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        await client.post(
            "/characters/conditions",
            params={"character_id": character.id},
            json={"condition": "EXHAUSTION", "exhaustion_level": 1},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        response = await client.patch(
            "/characters/conditions",
            params={"character_id": character.id, "condition": "EXHAUSTION"},
            json={"exhaustion_level": 4},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["exhaustion_level"] == 4

    async def test_update_non_exhaustion_condition_with_level_returns_400(
        self, client, player, player_token, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        await client.post(
            "/characters/conditions",
            params={"character_id": character.id},
            json={"condition": "POISONED"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        response = await client.patch(
            "/characters/conditions",
            params={"character_id": character.id, "condition": "POISONED"},
            json={"exhaustion_level": 2},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_remove_condition(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)
        await client.post(
            "/characters/conditions",
            params={"character_id": character.id},
            json={"condition": "POISONED"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        response = await client.delete(
            "/characters/conditions",
            params={"character_id": character.id, "condition": "POISONED"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 204
        assert (
            await client.get(
                "/characters/conditions",
                params={"character_id": character.id},
                headers={"Authorization": f"Bearer {player_token}"},
            )
        ).json() == []

    async def test_player_cannot_add_condition_to_other_players_character(
        self, client, player_token, create_user, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        other = await create_user(username="other", email="other@example.com")
        character = await create_character(owner_id=other.id, class_id=character_class.id)

        response = await client.post(
            "/characters/conditions",
            params={"character_id": character.id},
            json={"condition": "POISONED"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
