"""Tests for the feature write endpoints."""

import pytest


@pytest.mark.integration
class TestFeatureCrud:
    def test_player_cannot_create_feature(self, client, player_token):
        response = client.post(
            "/features/",
            json={"name": "Custom Feature", "source_type": "OTHER"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    def test_gm_can_create_other_feature(self, client, gm_token):
        response = client.post(
            "/features/",
            json={"name": "Custom Feature", "source_type": "OTHER"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert response.json()["name"] == "Custom Feature"
        assert response.json()["source_type"] == "OTHER"

    def test_gm_can_create_class_feature(self, client, gm_token, create_class):
        character_class = create_class(name="Fighter")

        response = client.post(
            "/features/",
            json={"name": "Extra Attack", "source_type": "CLASS", "class_id": character_class.id, "level": 5},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert response.json()["class_id"] == character_class.id
        assert response.json()["level"] == 5

    def test_create_feature_with_mismatched_fk_returns_422(self, client, gm_token, create_race):
        race = create_race(name="Elf")

        response = client.post(
            "/features/",
            json={"name": "Bad Feature", "source_type": "CLASS", "race_id": race.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    def test_gm_can_update_feature(self, client, gm_token, create_feature):
        feature = create_feature(name="Old Feature", source_type="OTHER")

        response = client.patch(
            f"/features/{feature.id}",
            json={"name": "New Feature"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "New Feature"

    def test_gm_can_delete_feature(self, client, gm_token, create_feature):
        feature = create_feature(name="Doomed Feature", source_type="OTHER")

        response = client.delete(f"/features/{feature.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 204
        assert client.get(f"/features/{feature.id}").status_code == 404
