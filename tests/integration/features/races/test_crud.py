"""Tests for the race write endpoints."""

import pytest


@pytest.mark.integration
class TestRaceCrud:
    def test_player_cannot_create_race(self, client, player_token):
        response = client.post(
            "/races/",
            json={"name": "Custom Race", "size": "MEDIUM", "speed": 30},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    def test_gm_can_create_race(self, client, gm_token):
        response = client.post(
            "/races/",
            json={"name": "Elf", "size": "MEDIUM", "speed": 30},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Elf"
        assert body["ability_bonuses"] == []

    def test_create_race_with_ability_bonuses_and_skills(self, client, gm_token, create_skill):
        skill = create_skill(key="PERCEPTION", name="Perception", ability="WIS")

        response = client.post(
            "/races/",
            json={
                "name": "Wood Elf",
                "size": "MEDIUM",
                "speed": 35,
                "ability_bonuses": [{"ability": "DEX", "bonus": 2}],
                "granted_skills": [skill.id],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["ability_bonuses"] == [{"ability": "DEX", "bonus": 2}]
        assert body["granted_skills"][0]["id"] == skill.id

    def test_create_race_with_nested_features(self, client, gm_token):
        response = client.post(
            "/races/",
            json={
                "name": "Drow",
                "size": "MEDIUM",
                "speed": 30,
                "features": [
                    {"name": "Darkvision", "description": "See in dim light within 60 ft."},
                    {"name": "Sunlight Sensitivity", "description": "Disadvantage in direct sunlight."},
                ],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        race_id = response.json()["id"]

        features = client.get(f"/features/?source_type=RACE&race_id={race_id}").json()["items"]
        assert [feature["name"] for feature in features] == ["Darkvision", "Sunlight Sensitivity"]
        assert all(feature["source_type"] == "RACE" and feature["race_id"] == race_id for feature in features)

    def test_create_duplicate_race_name_returns_400(self, client, gm_token, create_race):
        create_race(name="Orc")
        response = client.post(
            "/races/",
            json={"name": "Orc", "size": "MEDIUM", "speed": 30},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    def test_gm_can_update_race(self, client, gm_token, create_race):
        race = create_race(name="Old Name")

        response = client.patch(
            f"/races/{race.id}", json={"name": "New Name"}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

    def test_gm_can_replace_ability_bonuses(self, client, gm_token, create_race):
        race = create_race(name="Dragonborn")

        response = client.put(
            f"/races/{race.id}/ability-bonuses",
            json={"ability_bonuses": [{"ability": "STR", "bonus": 2}, {"ability": "CHA", "bonus": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        bonuses = {item["ability"]: item["bonus"] for item in response.json()["ability_bonuses"]}
        assert bonuses == {"STR": 2, "CHA": 1}

    def test_gm_can_clear_ability_bonuses(self, client, gm_token, create_race):
        race = create_race(name="Blank")

        response = client.put(
            f"/races/{race.id}/ability-bonuses",
            json={"ability_bonuses": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["ability_bonuses"] == []

    def test_gm_can_set_granted_skills(self, client, gm_token, create_race, create_skill):
        race = create_race(name="Skillful")
        skill = create_skill(key="STEALTH", name="Stealth", ability="DEX")

        response = client.put(
            f"/races/{race.id}/skills",
            json={"skill_ids": [skill.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["granted_skills"]] == [skill.id]

    def test_gm_can_delete_race(self, client, gm_token, create_race):
        race = create_race(name="Doomed Race")

        response = client.delete(f"/races/{race.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 204
        assert client.get(f"/races/{race.id}").status_code == 404

    def test_delete_race_in_use_by_character_returns_409(
        self, client, gm_token, create_race, create_class, create_user, create_character
    ):
        race = create_race(name="Popular Race")
        player = create_user()
        char_class = create_class(name="Some Class")
        create_character(owner_id=player.id, class_id=char_class.id, race_id=race.id)

        response = client.delete(f"/races/{race.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 409
