"""Tests for character attack endpoints."""

import pytest

ATTACK_PAYLOAD = {
    "name": "Longsword",
    "attack_type": "MELEE_ATTACK",
    "ability": "STR",
    "is_proficient": True,
    "damage_dice_count": 1,
    "damage_dice_type": "D8",
    "damage_type": "SLASHING",
}


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterAttacks:
    async def test_create_and_list_attacks(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        create_response = await client.post(
            "/characters/attacks",
            params={"character_id": character.id},
            json=ATTACK_PAYLOAD,
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert create_response.status_code == 201
        attack_id = create_response.json()["id"]

        list_response = await client.get(
            "/characters/attacks",
            params={"character_id": character.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert list_response.status_code == 200
        assert [item["id"] for item in list_response.json()] == [attack_id]

    async def test_update_attack(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        attack_response = await client.post(
            "/characters/attacks",
            params={"character_id": character.id},
            json=ATTACK_PAYLOAD,
            headers={"Authorization": f"Bearer {player_token}"},
        )
        attack_id = attack_response.json()["id"]

        response = await client.patch(
            "/characters/attacks",
            params={"character_id": character.id, "attack_id": attack_id},
            json={"name": "Masterwork Longsword"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Masterwork Longsword"

    async def test_delete_attack(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        attack_response = await client.post(
            "/characters/attacks",
            params={"character_id": character.id},
            json=ATTACK_PAYLOAD,
            headers={"Authorization": f"Bearer {player_token}"},
        )
        attack_id = attack_response.json()["id"]

        response = await client.delete(
            "/characters/attacks",
            params={"character_id": character.id, "attack_id": attack_id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 204
        assert (
            await client.get(
                "/characters/attacks",
                params={"character_id": character.id},
                headers={"Authorization": f"Bearer {player_token}"},
            )
        ).json() == []

    async def test_player_cannot_manage_other_players_attacks(
        self, client, player_token, create_user, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        other = await create_user(username="other", email="other@example.com")
        character = await create_character(owner_id=other.id, class_id=character_class.id)

        response = await client.post(
            "/characters/attacks",
            params={"character_id": character.id},
            json=ATTACK_PAYLOAD,
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
