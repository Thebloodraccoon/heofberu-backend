"""Tests for character feature endpoints: record, update, remove."""

import pytest


@pytest.mark.integration
class TestCharacterFeatures:
    def test_add_and_list_feature(self, client, player, player_token, create_class, create_character, create_feature):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)
        feature = create_feature(name="Extra Attack", source_type="OTHER")

        add_response = client.post(
            f"/characters/{character.id}/features",
            json={"feature_id": feature.id, "notes": "Two attacks"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert add_response.status_code == 201
        assert add_response.json()["feature_id"] == feature.id
        assert add_response.json()["notes"] == "Two attacks"

        list_response = client.get(
            f"/characters/{character.id}/features",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert list_response.status_code == 200
        assert [item["feature_id"] for item in list_response.json()] == [feature.id]

    def test_response_embeds_brief_feature_details(
        self, client, player, player_token, create_class, create_character, create_feature
    ):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)
        feature = create_feature(name="Second Wind", source_type="CLASS", class_id=character_class.id, level=1)

        add_response = client.post(
            f"/characters/{character.id}/features",
            json={"feature_id": feature.id, "notes": "Once per short rest"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert add_response.status_code == 201
        embedded = add_response.json()["feature"]
        assert embedded["id"] == feature.id
        assert embedded["name"] == "Second Wind"
        assert embedded["source_type"] == "CLASS"
        # The payload stays light — full detail (description) is fetched
        # on demand via GET /features/{feature_id}.
        assert "description" not in embedded

    def test_gm_can_add_standalone_feature_to_player_character(
        self, client, gm_token, player, create_class, create_character, create_feature
    ):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)
        gift = create_feature(name="GM Gift", source_type="OTHER")

        response = client.post(
            f"/characters/{character.id}/features",
            json={"feature_id": gift.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert response.json()["feature_id"] == gift.id

    def test_add_missing_feature_returns_404(self, client, player, player_token, create_class, create_character):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)

        response = client.post(
            f"/characters/{character.id}/features",
            json={"feature_id": 999999},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 404

    def test_duplicate_feature_returns_409(
        self, client, player, player_token, create_class, create_character, create_feature
    ):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)
        feature = create_feature(name="Extra Attack", source_type="OTHER")

        client.post(
            f"/characters/{character.id}/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        response = client.post(
            f"/characters/{character.id}/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 409

    def test_update_feature_notes(self, client, player, player_token, create_class, create_character, create_feature):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)
        feature = create_feature(name="Fighting Style", source_type="OTHER")
        add_response = client.post(
            f"/characters/{character.id}/features",
            json={"feature_id": feature.id, "notes": "Defense"},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        character_feature_id = add_response.json()["id"]

        response = client.patch(
            f"/characters/{character.id}/features/{character_feature_id}",
            json={"notes": "Dueling"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["notes"] == "Dueling"

    def test_remove_feature(self, client, player, player_token, create_class, create_character, create_feature):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)
        feature = create_feature(name="Extra Attack", source_type="OTHER")
        add_response = client.post(
            f"/characters/{character.id}/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        character_feature_id = add_response.json()["id"]

        response = client.delete(
            f"/characters/{character.id}/features/{character_feature_id}",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 204
        assert (
            client.get(
                f"/characters/{character.id}/features",
                headers={"Authorization": f"Bearer {player_token}"},
            ).json()
            == []
        )

    def test_player_cannot_add_feature_to_other_players_character(
        self, client, player_token, create_user, create_class, create_character, create_feature
    ):
        character_class = create_class(name="Fighter")
        other = create_user(username="other", email="other@example.com")
        character = create_character(owner_id=other.id, class_id=character_class.id)
        feature = create_feature(name="Extra Attack", source_type="OTHER")

        response = client.post(
            f"/characters/{character.id}/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
