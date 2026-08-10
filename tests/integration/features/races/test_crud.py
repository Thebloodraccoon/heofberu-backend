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

        fetched = await client.get(f"/races/{race_id}")
        assert fetched.status_code == 200
        assert [feature["name"] for feature in fetched.json()["features"]] == [
            "Darkvision",
            "Sunlight Sensitivity",
        ]

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

    async def test_player_cannot_add_race_feature(self, client, player_token, create_race):
        race = await create_race(name="Elf")

        response = await client.post(
            f"/races/{race.id}/features",
            json={"name": "Darkvision"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_add_update_and_remove_race_features(self, client, gm_token, create_race):
        race = await create_race(name="Elf")

        added = await client.post(
            f"/races/{race.id}/features",
            json={"name": "Darkvision", "description": "See in dim light within 60 ft."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert added.status_code == 201
        feature = added.json()["features"][0]
        assert feature["name"] == "Darkvision"

        updated = await client.patch(
            f"/races/{race.id}/features/{feature['id']}",
            json={"description": "See in dim light within 120 ft."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert updated.status_code == 200
        updated_feature = updated.json()["features"][0]
        assert updated_feature["id"] == feature["id"]
        assert updated_feature["description"] == "See in dim light within 120 ft."

        removed = await client.delete(
            f"/races/{race.id}/features/{feature['id']}",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert removed.status_code == 204
        fetched = await client.get(f"/races/{race.id}")
        assert fetched.json()["features"] == []

    async def test_update_race_feature_of_another_source_returns_400(
        self, client, gm_token, create_race, create_feature
    ):
        race = await create_race(name="Elf")
        foreign = await create_feature(name="Alien Feature", source_type="OTHER")

        response = await client.patch(
            f"/races/{race.id}/features/{foreign.id}",
            json={"name": "Renamed"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_remove_race_feature_of_another_source_returns_400(
        self, client, gm_token, create_race, create_feature
    ):
        race = await create_race(name="Elf")
        foreign = await create_feature(name="Alien Feature", source_type="OTHER")

        response = await client.delete(
            f"/races/{race.id}/features/{foreign.id}",
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 400

    async def test_race_feature_endpoints_return_404(self, client, gm_token):
        assert (
            await client.post(
                "/races/9999/features",
                json={"name": "Darkvision"},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).status_code == 404
        assert (
            await client.patch(
                "/races/9999/features/1",
                json={"name": "Renamed"},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).status_code == 404
        assert (
            await client.delete(
                "/races/9999/features/1",
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).status_code == 404
