"""Tests for the item read endpoints."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestItemOpenRead:
    async def test_list_items(self, client, create_item):
        await create_item(name="Longsword", item_type="WEAPON")
        await create_item(name="Leather Armor", item_type="ARMOR")

        response = await client.get("/items")

        assert response.status_code == 200
        names = {item["name"] for item in response.json()["items"]}
        assert {"Longsword", "Leather Armor"} <= names

    async def test_list_items_filters_by_type_and_rarity(self, client, create_item):
        await create_item(name="Longsword", item_type="WEAPON", rarity="NONE")
        await create_item(name="Cloak of Protection", item_type="WONDROUS_ITEM", rarity="UNCOMMON")

        response = await client.get("/items?item_type=WEAPON")

        assert response.status_code == 200
        assert all(item["item_type"] == "WEAPON" for item in response.json()["items"])

        rarity_response = await client.get("/items?rarity=UNCOMMON")
        assert [item["name"] for item in rarity_response.json()["items"]] == ["Cloak of Protection"]

    async def test_get_item_by_id(self, client, create_item):
        item = await create_item(name="Longsword", item_type="WEAPON")

        response = await client.get(f"/items/{item.id}")

        assert response.status_code == 200
        assert response.json()["name"] == "Longsword"

    async def test_get_item_404(self, client):
        assert (await client.get("/items/999999")).status_code == 404
