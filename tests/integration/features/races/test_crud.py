"""Tests for the race write endpoints."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestRaceCrud:
    async def test_player_cannot_create_race(self, client, player_token):
        response = await client.post(
            "/races",
            json={"name": "Custom Race", "size": "MEDIUM", "speed": 30},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_create_race(self, client, gm_token):
        response = await client.post(
            "/races",
            json={"name": "Elf", "size": "MEDIUM", "speed": 30},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Elf"
        assert body["ability_bonuses"] == []

    async def test_create_race_with_ability_bonuses_and_skills(self, client, gm_token, create_skill):
        skill = await create_skill(key="PERCEPTION", name="Perception", ability="WIS")

        response = await client.post(
            "/races",
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

    async def test_create_race_with_nested_features(self, client, gm_token):
        response = await client.post(
            "/races",
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

        features = (await client.get(f"/features?source_type=RACE&race_id={race_id}")).json()["items"]
        assert [feature["name"] for feature in features] == ["Darkvision", "Sunlight Sensitivity"]
        assert all(feature["source_type"] == "RACE" and feature["race_id"] == race_id for feature in features)

    async def test_create_duplicate_race_name_returns_400(self, client, gm_token, create_race):
        await create_race(name="Orc")
        response = await client.post(
            "/races",
            json={"name": "Orc", "size": "MEDIUM", "speed": 30},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_gm_can_update_race(self, client, gm_token, create_race):
        race = await create_race(name="Old Name")

        response = await client.patch(
            f"/races/{race.id}", json={"name": "New Name"}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

    async def test_gm_can_replace_ability_bonuses(self, client, gm_token, create_race):
        race = await create_race(name="Dragonborn")

        response = await client.put(
            f"/races/{race.id}/ability-bonuses",
            json={"ability_bonuses": [{"ability": "STR", "bonus": 2}, {"ability": "CHA", "bonus": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        bonuses = {item["ability"]: item["bonus"] for item in response.json()["ability_bonuses"]}
        assert bonuses == {"STR": 2, "CHA": 1}

    async def test_gm_can_clear_ability_bonuses(self, client, gm_token, create_race):
        race = await create_race(name="Blank")

        response = await client.put(
            f"/races/{race.id}/ability-bonuses",
            json={"ability_bonuses": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["ability_bonuses"] == []

    async def test_gm_can_set_granted_skills(self, client, gm_token, create_race, create_skill):
        race = await create_race(name="Skillful")
        skill = await create_skill(key="STEALTH", name="Stealth", ability="DEX")

        response = await client.put(
            f"/races/{race.id}/skills",
            json={"skill_ids": [skill.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["granted_skills"]] == [skill.id]

    async def test_gm_cannot_delete_race(self, client, gm_token, create_race):
        race = await create_race(name="Doomed Race")

        response = await client.delete(f"/races/{race.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 403
        assert (await client.get(f"/races/{race.id}")).status_code == 200

    async def test_founder_can_delete_race(self, client, founder_token, create_race):
        race = await create_race(name="Doomed Race")

        response = await client.delete(f"/races/{race.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 204
        assert (await client.get(f"/races/{race.id}")).status_code == 404

    async def test_delete_race_in_use_by_character_returns_409(
        self, client, founder_token, create_race, create_class, create_user, create_character
    ):
        race = await create_race(name="Popular Race")
        player = await create_user()
        char_class = await create_class(name="Some Class")
        await create_character(owner_id=player.id, class_id=char_class.id, race_id=race.id)

        response = await client.delete(f"/races/{race.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 409

    async def test_player_cannot_replace_race_features(self, client, player_token, create_race):
        race = await create_race(name="Elf")

        response = await client.put(
            f"/races/{race.id}/features",
            json={"features": [{"name": "Darkvision"}]},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_replace_race_features_by_id(self, client, gm_token):
        created = await client.post(
            "/races",
            json={
                "name": "Elf",
                "size": "MEDIUM",
                "speed": 30,
                "features": [
                    {"name": "Darkvision", "description": "See in dim light within 60 ft."},
                    {"name": "Fey Ancestry", "description": "Advantage on saves vs charm."},
                ],
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert created.status_code == 201
        race_id = created.json()["id"]
        original = {feature["name"]: feature["id"] for feature in created.json()["features"]}

        response = await client.put(
            f"/races/{race_id}/features",
            json={
                "features": [
                    {"id": original["Darkvision"], "name": "Darkvision", "description": "See in the dark."},
                    {"name": "Trance", "description": "Meditate for 4 hours instead of sleeping."},
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        features = {feature["name"]: feature for feature in response.json()["features"]}
        assert set(features) == {"Darkvision", "Trance"}
        # Kept id → updated in place (grants survive); no id → created.
        assert features["Darkvision"]["id"] == original["Darkvision"]
        trance_id = features["Trance"]["id"]
        assert (await client.get(f"/features/{trance_id}")).json()["source_type"] == "RACE"
        # Feature absent from the payload is gone.
        assert (await client.get(f"/features/{original['Fey Ancestry']}")).status_code == 404

    async def test_replace_race_features_unknown_id_returns_400(self, client, gm_token, create_race, create_feature):
        race = await create_race(name="Elf")
        foreign = await create_feature(name="Alien Feature", source_type="OTHER")

        response = await client.put(
            f"/races/{race.id}/features",
            json={"features": [{"id": foreign.id, "name": "Alien Feature"}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_gm_can_clear_race_features(self, client, gm_token, create_race, create_feature):
        race = await create_race(name="Elf")
        await create_feature(name="Darkvision", source_type="RACE", race_id=race.id)

        response = await client.put(
            f"/races/{race.id}/features",
            json={"features": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json()["features"] == []

    async def test_replace_race_features_returns_404(self, client, gm_token):
        response = await client.put(
            "/races/9999/features",
            json={"features": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 404
