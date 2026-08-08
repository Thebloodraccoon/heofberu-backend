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

    def test_cannot_create_class_feature_directly(self, client, gm_token, create_class):
        character_class = create_class(name="Fighter")

        response = client.post(
            "/features/",
            json={"name": "Extra Attack", "source_type": "CLASS", "class_id": character_class.id, "level": 5},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    def test_cannot_create_subclass_feature_directly(self, client, gm_token, create_class, create_subclass):
        character_class = create_class(name="Fighter")
        subclass = create_subclass(class_id=character_class.id, name="Champion")

        response = client.post(
            "/features/",
            json={"name": "Improved Critical", "source_type": "SUBCLASS", "subclass_id": subclass.id, "level": 3},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    @pytest.mark.parametrize(
        "source_type,fk_name",
        [
            ("RACE", "race_id"),
            ("BACKGROUND", "background_id"),
            ("FEAT", "feat_id"),
        ],
    )
    def test_cannot_create_source_owned_feature_directly(
        self, client, gm_token, create_race, create_background, create_feat, source_type, fk_name
    ):
        parent_by_type = {
            "RACE": create_race(name="Elf"),
            "BACKGROUND": create_background(name="Acolyte"),
            "FEAT": create_feat(name="Alert"),
        }
        parent = parent_by_type[source_type]

        response = client.post(
            "/features/",
            json={"name": "Owned Feature", "source_type": source_type, fk_name: parent.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    def test_other_feature_cannot_set_source_fk(self, client, gm_token, create_class):
        character_class = create_class(name="Fighter")

        response = client.post(
            "/features/",
            json={"name": "Bad Feature", "source_type": "OTHER", "class_id": character_class.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

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

    def test_cannot_update_feature_source(self, client, gm_token, create_feature):
        feature = create_feature(name="Old Feature", source_type="OTHER")

        response = client.patch(
            f"/features/{feature.id}",
            json={"source_type": "FEAT"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    def test_cannot_set_level_on_other_feature(self, client, gm_token, create_feature):
        feature = create_feature(name="Old Feature", source_type="OTHER")

        response = client.patch(
            f"/features/{feature.id}",
            json={"level": 5},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    def test_gm_can_delete_feature(self, client, gm_token, create_feature):
        feature = create_feature(name="Doomed Feature", source_type="OTHER")

        response = client.delete(f"/features/{feature.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 204
        assert client.get(f"/features/{feature.id}").status_code == 404

    def test_cannot_update_source_owned_feature_via_features_crud(self, client, gm_token, create_class, create_feature):
        character_class = create_class(name="Fighter")
        feature = create_feature(name="Extra Attack", source_type="CLASS", class_id=character_class.id, level=5)

        response = client.patch(
            f"/features/{feature.id}",
            json={"name": "Renamed"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400
        assert client.get(f"/features/{feature.id}").json()["name"] == "Extra Attack"

    def test_cannot_delete_source_owned_feature_via_features_crud(self, client, gm_token, create_race, create_feature):
        race = create_race(name="Elf")
        feature = create_feature(name="Darkvision", source_type="RACE", race_id=race.id)

        response = client.delete(f"/features/{feature.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 400
        assert client.get(f"/features/{feature.id}").status_code == 200
