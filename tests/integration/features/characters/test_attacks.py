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
class TestCharacterAttacks:
    def test_create_and_list_attacks(self, client, player, player_token, create_class, create_character):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)

        create_response = client.post(
            f"/characters/{character.id}/attacks",
            json=ATTACK_PAYLOAD,
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert create_response.status_code == 201
        attack_id = create_response.json()["id"]

        list_response = client.get(
            f"/characters/{character.id}/attacks",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert list_response.status_code == 200
        assert [item["id"] for item in list_response.json()] == [attack_id]

    def test_update_attack(self, client, player, player_token, create_class, create_character):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)

        attack_response = client.post(
            f"/characters/{character.id}/attacks",
            json=ATTACK_PAYLOAD,
            headers={"Authorization": f"Bearer {player_token}"},
        )
        attack_id = attack_response.json()["id"]

        response = client.patch(
            f"/characters/{character.id}/attacks/{attack_id}",
            json={"name": "Masterwork Longsword"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Masterwork Longsword"

    def test_delete_attack(self, client, player, player_token, create_class, create_character):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)

        attack_response = client.post(
            f"/characters/{character.id}/attacks",
            json=ATTACK_PAYLOAD,
            headers={"Authorization": f"Bearer {player_token}"},
        )
        attack_id = attack_response.json()["id"]

        response = client.delete(
            f"/characters/{character.id}/attacks/{attack_id}",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 204
        assert (
            client.get(
                f"/characters/{character.id}/attacks",
                headers={"Authorization": f"Bearer {player_token}"},
            ).json()
            == []
        )

    def test_player_cannot_manage_other_players_attacks(
        self, client, player_token, create_user, create_class, create_character
    ):
        character_class = create_class(name="Fighter")
        other = create_user(username="other", email="other@example.com")
        character = create_character(owner_id=other.id, class_id=character_class.id)

        response = client.post(
            f"/characters/{character.id}/attacks",
            json=ATTACK_PAYLOAD,
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
