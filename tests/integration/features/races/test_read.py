"""Tests for the race read endpoints."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestRaceOpenRead:
    async def test_list_races(self, client, create_race):
        await create_race(name="Elf", size="MEDIUM", speed=30)
        await create_race(name="Dwarf", size="MEDIUM", speed=25)

        response = await client.get("/races")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 2
        names = {item["name"] for item in body["items"]}
        assert {"Elf", "Dwarf"} <= names

    async def test_list_races_filters_by_size_and_search(self, client, create_race):
        await create_race(name="Halfling", size="SMALL", speed=25)
        await create_race(name="Human", size="MEDIUM", speed=30)

        response = await client.get("/races?race_size=SMALL")

        assert response.status_code == 200
        assert all(item["size"] == "SMALL" for item in response.json()["items"])

        search_response = await client.get("/races?search=halfling")
        assert search_response.json()["total"] >= 1

    async def test_get_race_by_id(self, client, create_race):
        race = await create_race(name="Tiefling")

        response = await client.get(f"/races/{race.id}")

        assert response.status_code == 200
        assert response.json()["name"] == "Tiefling"
        assert response.json()["size"] == "MEDIUM"

    async def test_get_race_by_id_embeds_features(self, client, gm_token):
        created = await client.post(
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
        assert created.status_code == 201
        race_id = created.json()["id"]

        response = await client.get(f"/races/{race_id}")

        assert response.status_code == 200
        assert [feature["name"] for feature in response.json()["features"]] == [
            "Darkvision",
            "Sunlight Sensitivity",
        ]

    async def test_get_race_by_id_reflects_feature_edits(self, client, gm_token, create_race):
        race = await create_race(name="Elf")

        added = await client.post(
            "/features",
            json={
                "name": "Darkvision",
                "description": "See in dim light within 60 ft.",
                "source_type": "RACE",
                "race_id": race.id,
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert added.status_code == 201
        feature_id = added.json()["id"]

        first_fetch = await client.get(f"/races/{race.id}")
        assert first_fetch.status_code == 200
        assert first_fetch.json()["features"][0]["description"] == "See in dim light within 60 ft."

        updated = await client.patch(
            f"/features/{feature_id}",
            json={"description": "See in dim light within 120 ft."},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert updated.status_code == 200

        fresh_fetch = await client.get(f"/races/{race.id}")
        assert fresh_fetch.status_code == 200
        assert fresh_fetch.json()["features"][0]["description"] == "See in dim light within 120 ft."

    async def test_get_race_404(self, client):
        response = await client.get("/races/999999")

        assert response.status_code == 404
