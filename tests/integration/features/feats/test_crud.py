"""Tests for the feat write endpoints."""

import pytest


@pytest.mark.integration
class TestFeatCrud:
    def test_player_cannot_create_feat(self, client, player_token):
        response = client.post(
            "/feats/",
            json={"name": "Custom Feat"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    def test_gm_can_create_feat(self, client, gm_token):
        response = client.post(
            "/feats/",
            json={"name": "Alert"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert response.json()["name"] == "Alert"

    def test_create_duplicate_feat_name_returns_400(self, client, gm_token, create_feat):
        create_feat(name="Lucky")
        response = client.post(
            "/feats/",
            json={"name": "Lucky"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    def test_gm_can_update_feat(self, client, gm_token, create_feat):
        feat = create_feat(name="Old Name")

        response = client.patch(
            f"/feats/{feat.id}", json={"name": "New Name"}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

    def test_gm_can_set_ability_score_increases(self, client, gm_token, create_feat):
        feat = create_feat(name="Resilient")

        response = client.put(
            f"/feats/{feat.id}/ability-score-increases",
            json={"ability_score_increases": [{"ability": "STR", "amount": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert {item["ability"]: item["amount"] for item in response.json()["ability_score_increases"]} == {"STR": 1}

    def test_gm_can_create_feat_with_nested_features(self, client, gm_token):
        response = client.post(
            "/feats/",
            json={
                "name": "Alert",
                "features": [
                    {"name": "Alert Initiative", "description": "You gain a +5 bonus to initiative."},
                    {"name": "Cannot Be Surprised", "description": "You can't be surprised while conscious."},
                ],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert [item["name"] for item in response.json()["features"]] == ["Alert Initiative", "Cannot Be Surprised"]

        feat_id = response.json()["id"]
        listed = client.get(f"/features/?source_type=FEAT&feat_id={feat_id}")
        assert listed.status_code == 200
        assert [item["name"] for item in listed.json()["items"]] == ["Alert Initiative", "Cannot Be Surprised"]

    def test_gm_cannot_delete_feat(self, client, gm_token, create_feat):
        feat = create_feat(name="Doomed Feat")

        response = client.delete(f"/feats/{feat.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 403
        assert client.get(f"/feats/{feat.id}").status_code == 200

    def test_founder_can_delete_feat(self, client, founder_token, create_feat):
        feat = create_feat(name="Doomed Feat")

        response = client.delete(f"/feats/{feat.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 204
        assert client.get(f"/feats/{feat.id}").status_code == 404

    def test_founder_can_delete_feat_with_features_cascades_them(self, client, founder_token, create_feat):
        create_feat(name="Doomed Feat")

        response = client.post(
            "/feats/",
            json={"name": "With Benefit", "features": [{"name": "Benefit", "description": "Something useful."}]},
            headers={"Authorization": f"Bearer {founder_token}"},
        )
        assert response.status_code == 201
        feat_id = response.json()["id"]
        feature_id = response.json()["features"][0]["id"]

        delete_response = client.delete(f"/feats/{feat_id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert delete_response.status_code == 204
        assert client.get(f"/feats/{feat_id}").status_code == 404
        assert client.get(f"/features/{feature_id}").status_code == 404

    def test_delete_feat_granted_to_character_returns_409(
        self, client, founder_token, player_token, player, create_class, create_character, create_feat
    ):
        feat = create_feat(name="Popular Feat")
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)

        add_response = client.post(
            f"/characters/{character.id}/feats",
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert add_response.status_code == 201

        response = client.delete(f"/feats/{feat.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 409
        assert client.get(f"/feats/{feat.id}").status_code == 200

    def test_player_cannot_replace_feat_features(self, client, player_token, create_feat):
        feat = create_feat(name="Alert")

        response = client.put(
            f"/feats/{feat.id}/features",
            json={"features": [{"name": "Alert Initiative"}]},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    def test_gm_can_replace_feat_features_by_id(self, client, gm_token):
        created = client.post(
            "/feats/",
            json={
                "name": "Alert",
                "features": [
                    {"name": "Alert Initiative", "description": "You gain a +5 bonus to initiative."},
                    {"name": "Cannot Be Surprised", "description": "You can't be surprised while conscious."},
                ],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert created.status_code == 201
        feat_id = created.json()["id"]
        original = {feature["name"]: feature["id"] for feature in created.json()["features"]}

        response = client.put(
            f"/feats/{feat_id}/features",
            json={
                "features": [
                    {
                        "id": original["Alert Initiative"],
                        "name": "Alert Initiative",
                        "description": "You gain a +10 bonus to initiative.",
                    },
                    {"name": "Never Startled", "description": "You always act in the surprise round."},
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        features = {feature["name"]: feature for feature in response.json()["features"]}
        assert set(features) == {"Alert Initiative", "Never Startled"}
        # Kept id → updated in place (grants survive); no id → created.
        assert features["Alert Initiative"]["id"] == original["Alert Initiative"]
        assert features["Never Startled"]["source_type"] == "FEAT"
        # Feature absent from the payload is gone.
        assert client.get(f"/features/{original['Cannot Be Surprised']}").status_code == 404

    def test_replace_feat_features_unknown_id_returns_400(self, client, gm_token, create_feat, create_feature):
        feat = create_feat(name="Alert")
        foreign = create_feature(name="Alien Feature", source_type="OTHER")

        response = client.put(
            f"/feats/{feat.id}/features",
            json={"features": [{"id": foreign.id, "name": "Alien Feature"}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    def test_gm_can_clear_feat_features(self, client, gm_token, create_feat, create_feature):
        feat = create_feat(name="Alert")
        create_feature(name="Alert Initiative", source_type="FEAT", feat_id=feat.id)

        response = client.put(
            f"/feats/{feat.id}/features",
            json={"features": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["features"] == []

    def test_replace_feat_features_returns_404(self, client, gm_token):
        response = client.put(
            "/feats/9999/features",
            json={"features": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404

    def test_delete_feat_whose_feature_is_granted_to_character_returns_409(
        self,
        client,
        founder_token,
        player_token,
        player,
        create_class,
        create_character,
        create_feat,
        create_feature,
    ):
        feat = create_feat(name="Popular Feat")
        benefit = create_feature(name="Benefit", source_type="FEAT", feat_id=feat.id)
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)

        add_response = client.post(
            f"/characters/{character.id}/features",
            json={"feature_id": benefit.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert add_response.status_code == 201

        response = client.delete(f"/feats/{feat.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 409
        assert client.get(f"/feats/{feat.id}").status_code == 200
