"""Tests for the background write endpoints."""

import pytest


@pytest.mark.integration
class TestBackgroundCrud:
    def test_player_cannot_create_background(self, client, player_token):
        response = client.post(
            "/backgrounds/",
            json={"name": "Custom"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    def test_gm_can_create_background(self, client, gm_token):
        response = client.post(
            "/backgrounds/",
            json={"name": "Hermit"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert response.json()["name"] == "Hermit"

    def test_create_duplicate_background_name_returns_400(self, client, gm_token, create_background):
        create_background(name="Acolyte")
        response = client.post(
            "/backgrounds/",
            json={"name": "Acolyte"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    def test_gm_can_set_granted_skills(self, client, gm_token, create_background, create_skill):
        background = create_background(name="Sage")
        skill = create_skill(key="ARCANA", name="Arcana", ability="INT")

        response = client.put(
            f"/backgrounds/{background.id}/skills",
            json={"skill_ids": [skill.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["granted_skills"]] == [skill.id]

    def test_gm_can_create_background_with_nested_features(self, client, gm_token):
        response = client.post(
            "/backgrounds/",
            json={
                "name": "Acolyte",
                "features": [
                    {"name": "Shelter of the Faithful", "description": "Free healing and care at a temple."},
                ],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        assert [item["name"] for item in response.json()["features"]] == ["Shelter of the Faithful"]

        background_id = response.json()["id"]
        listed = client.get(f"/features/?source_type=BACKGROUND&background_id={background_id}")
        assert listed.status_code == 200
        assert [item["name"] for item in listed.json()["items"]] == ["Shelter of the Faithful"]

    def test_gm_cannot_delete_background(self, client, gm_token, create_background):
        background = create_background(name="Doomed Background")

        response = client.delete(f"/backgrounds/{background.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 403
        assert client.get(f"/backgrounds/{background.id}").status_code == 200

    def test_founder_can_delete_background(self, client, founder_token, create_background):
        background = create_background(name="Doomed Background")

        response = client.delete(f"/backgrounds/{background.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 204
        assert client.get(f"/backgrounds/{background.id}").status_code == 404

    def test_delete_background_whose_feature_is_granted_to_character_returns_409(
        self,
        client,
        founder_token,
        player_token,
        player,
        create_class,
        create_character,
        create_background,
        create_feature,
    ):
        background = create_background(name="Popular Background")
        shelter = create_feature(name="Shelter of the Faithful", source_type="BACKGROUND", background_id=background.id)
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)

        add_response = client.post(
            f"/characters/{character.id}/features",
            json={"feature_id": shelter.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert add_response.status_code == 201

        response = client.delete(f"/backgrounds/{background.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 409
        assert client.get(f"/backgrounds/{background.id}").status_code == 200

    def test_player_cannot_replace_background_features(self, client, player_token, create_background):
        background = create_background(name="Acolyte")

        response = client.put(
            f"/backgrounds/{background.id}/features",
            json={"features": [{"name": "Shelter of the Faithful"}]},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    def test_gm_can_replace_background_features_by_id(self, client, gm_token):
        created = client.post(
            "/backgrounds/",
            json={
                "name": "Acolyte",
                "features": [
                    {"name": "Shelter of the Faithful", "description": "Receive free healing at a temple."},
                    {"name": "Zealot", "description": "Spend an hour proselytizing."},
                ],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert created.status_code == 201
        background_id = created.json()["id"]
        original = {feature["name"]: feature["id"] for feature in created.json()["features"]}

        response = client.put(
            f"/backgrounds/{background_id}/features",
            json={
                "features": [
                    {
                        "id": original["Shelter of the Faithful"],
                        "name": "Shelter of the Faithful",
                        "description": "Free healing and care at a shrine.",
                    },
                    {"name": "Devotion", "description": "You have a personal devotional practice."},
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        features = {feature["name"]: feature for feature in response.json()["features"]}
        assert set(features) == {"Shelter of the Faithful", "Devotion"}
        # Kept id → updated in place (grants survive); no id → created.
        assert features["Shelter of the Faithful"]["id"] == original["Shelter of the Faithful"]
        # Feature absent from the payload is gone.
        assert client.get(f"/features/{original['Zealot']}").status_code == 404

    def test_replace_background_features_unknown_id_returns_400(
        self, client, gm_token, create_background, create_feature
    ):
        background = create_background(name="Acolyte")
        foreign = create_feature(name="Alien Feature", source_type="OTHER")

        response = client.put(
            f"/backgrounds/{background.id}/features",
            json={"features": [{"id": foreign.id, "name": "Alien Feature"}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    def test_gm_can_clear_background_features(self, client, gm_token, create_background, create_feature):
        background = create_background(name="Acolyte")
        create_feature(name="Shelter of the Faithful", source_type="BACKGROUND", background_id=background.id)

        response = client.put(
            f"/backgrounds/{background.id}/features",
            json={"features": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["features"] == []

    def test_replace_background_features_returns_404(self, client, gm_token):
        response = client.put(
            "/backgrounds/9999/features",
            json={"features": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404
