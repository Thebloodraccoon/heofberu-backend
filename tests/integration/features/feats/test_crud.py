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

    def test_gm_can_delete_feat(self, client, gm_token, create_feat):
        feat = create_feat(name="Doomed Feat")

        response = client.delete(f"/feats/{feat.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 204
        assert client.get(f"/feats/{feat.id}").status_code == 404
