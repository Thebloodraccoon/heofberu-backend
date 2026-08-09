"""Tests for the spell read endpoints."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestSpellOpenRead:
    async def test_list_spells(self, client, create_spell):
        await create_spell(name="Magic Missile", school="EVOCATION", level="LEVEL_1")
        await create_spell(name="Fireball", school="EVOCATION", level="LEVEL_3")

        response = await client.get("/spells/")

        assert response.status_code == 200
        names = {item["name"] for item in response.json()["items"]}
        assert {"Magic Missile", "Fireball"} <= names

    async def test_list_spells_filters_by_level(self, client, create_spell):
        await create_spell(name="Cure Wounds", school="EVOCATION", level="LEVEL_1")
        await create_spell(name="Fireball", school="EVOCATION", level="LEVEL_3")

        response = await client.get("/spells/?level=LEVEL_3")

        assert response.status_code == 200
        assert [item["name"] for item in response.json()["items"]] == ["Fireball"]

    async def test_get_spell_by_id(self, client, create_spell):
        spell = await create_spell(name="Detect Magic", school="DIVINATION", level="LEVEL_1")

        response = await client.get(f"/spells/{spell.id}")

        assert response.status_code == 200
        assert response.json()["name"] == "Detect Magic"
        assert response.json()["school"] == "DIVINATION"

    async def test_get_spell_404(self, client):
        assert (await client.get("/spells/999999")).status_code == 404
