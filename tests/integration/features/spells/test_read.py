"""Tests for the spell read endpoints."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestSpellOpenRead:
    async def test_list_spells(self, client, create_spell):
        await create_spell(name="Magic Missile", school="EVOCATION", level="LEVEL_1")
        await create_spell(name="Fireball", school="EVOCATION", level="LEVEL_3")

        response = await client.get("/spells")

        assert response.status_code == 200
        names = {item["name"] for item in response.json()["items"]}
        assert {"Magic Missile", "Fireball"} <= names

    async def test_list_spells_filters_by_level(self, client, create_spell):
        await create_spell(name="Cure Wounds", school="EVOCATION", level="LEVEL_1")
        await create_spell(name="Fireball", school="EVOCATION", level="LEVEL_3")

        response = await client.get("/spells?level=LEVEL_3")

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


@pytest.mark.integration
@pytest.mark.asyncio
class TestSpellCursorPagination:
    async def test_cursor_walks_every_spell_once_in_name_order(self, client, create_spell):
        for name in ("Bless", "Aid", "Dust", "Cure Wounds", "Bane"):
            await create_spell(name=name)

        names, cursor = [], None
        while True:
            params = {"pagination": "cursor", "size": 2, **({"cursor": cursor} if cursor else {})}
            body = (await client.get("/spells", params=params)).json()
            assert set(body) == {"items", "next_cursor", "size"}
            names.extend(item["name"] for item in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                break

        assert names == ["Aid", "Bane", "Bless", "Cure Wounds", "Dust"]

    async def test_cursor_respects_filters(self, client, create_spell):
        await create_spell(name="Cure Wounds", level="LEVEL_1")
        await create_spell(name="Fireball", level="LEVEL_3")

        body = (await client.get("/spells", params={"pagination": "cursor", "level": "LEVEL_3"})).json()

        assert [item["name"] for item in body["items"]] == ["Fireball"]
        assert body["next_cursor"] is None

    async def test_default_listing_stays_offset_paginated(self, client, create_spell):
        await create_spell(name="Aid")

        body = (await client.get("/spells")).json()

        assert {"items", "total", "page", "size"} <= set(body)

    @pytest.mark.parametrize("cursor", ["garbage!", "e30", "x" * 600])
    async def test_invalid_cursor_is_rejected(self, client, cursor):
        assert (await client.get("/spells", params={"cursor": cursor})).status_code == 422
