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

    async def test_get_race_404(self, client):
        response = await client.get("/races/999999")

        assert response.status_code == 404
