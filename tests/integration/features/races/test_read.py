"""Tests for the race read endpoints."""

import pytest


@pytest.mark.integration
class TestRaceOpenRead:
    def test_list_races(self, client, create_race):
        create_race(name="Elf", size="MEDIUM", speed=30)
        create_race(name="Dwarf", size="MEDIUM", speed=25)

        response = client.get("/races/")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 2
        names = {item["name"] for item in body["items"]}
        assert {"Elf", "Dwarf"} <= names

    def test_list_races_filters_by_size_and_search(self, client, create_race):
        create_race(name="Halfling", size="SMALL", speed=25)
        create_race(name="Human", size="MEDIUM", speed=30)

        response = client.get("/races/?race_size=SMALL")

        assert response.status_code == 200
        assert all(item["size"] == "SMALL" for item in response.json()["items"])

        search_response = client.get("/races/?search=halfling")
        assert search_response.json()["total"] >= 1

    def test_get_race_by_id(self, client, create_race):
        race = create_race(name="Tiefling")

        response = client.get(f"/races/{race.id}")

        assert response.status_code == 200
        assert response.json()["name"] == "Tiefling"
        assert response.json()["size"] == "MEDIUM"

    def test_get_race_404(self, client):
        response = client.get("/races/999999")

        assert response.status_code == 404
