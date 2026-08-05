"""Tests for character feat endpoints: grant, update, revoke."""

import pytest


@pytest.mark.integration
class TestCharacterFeats:
    def test_grant_and_list_feat(self, client, player, player_token, create_class, create_character, create_feat):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)
        feat = create_feat(name="Alert")

        grant_response = client.post(
            f"/characters/{character.id}/feats",
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert grant_response.status_code == 201
        assert grant_response.json()["feat_id"] == feat.id

        list_response = client.get(
            f"/characters/{character.id}/feats",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert list_response.status_code == 200
        assert [item["feat_id"] for item in list_response.json()] == [feat.id]

    def test_duplicate_feat_grant_returns_409(
        self, client, player, player_token, create_class, create_character, create_feat
    ):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)
        feat = create_feat(name="Alert")

        client.post(
            f"/characters/{character.id}/feats",
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        response = client.post(
            f"/characters/{character.id}/feats",
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 409

    def test_grant_feat_whose_prerequisite_is_unmet_returns_400(
        self, client, player, player_token, create_class, create_character, create_feat
    ):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)
        feat = create_feat(
            name="Heavy Armor Master",
            prerequisite_ability="STR",
            prerequisite_minimum_score=13,
        )

        response = client.post(
            f"/characters/{character.id}/feats",
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    def test_grant_feat_with_asi_choice(
        self, client, player, player_token, gm_token, create_class, create_character, create_feat
    ):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id, strength=13)
        feat = create_feat(name="Resilient")
        asi_response = client.put(
            f"/feats/{feat.id}/ability-score-increases",
            json={"ability_score_increases": [{"ability": "STR", "amount": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert asi_response.status_code == 200
        asi_id = asi_response.json()["ability_score_increases"][0]["id"]

        grant_response = client.post(
            f"/characters/{character.id}/feats",
            json={"feat_id": feat.id, "ability_score_increase_id": asi_id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert grant_response.status_code == 201
        assert grant_response.json()["ability_score_increase_id"] == asi_id

    def test_revoke_feat(self, client, player, player_token, create_class, create_character, create_feat):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)
        feat = create_feat(name="Alert")

        grant_response = client.post(
            f"/characters/{character.id}/feats",
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        character_feat_id = grant_response.json()["id"]

        response = client.delete(
            f"/characters/{character.id}/feats/{character_feat_id}",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 204
        assert (
            client.get(
                f"/characters/{character.id}/feats",
                headers={"Authorization": f"Bearer {player_token}"},
            ).json()
            == []
        )

    def test_player_cannot_grant_feat_to_other_players_character(
        self, client, player_token, create_user, create_class, create_character, create_feat
    ):
        character_class = create_class(name="Fighter")
        other = create_user(username="other", email="other@example.com")
        character = create_character(owner_id=other.id, class_id=character_class.id)
        feat = create_feat(name="Alert")

        response = client.post(
            f"/characters/{character.id}/feats",
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
