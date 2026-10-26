"""Tests for the item read endpoints."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestItemOpenRead:
    async def test_list_items(self, client, create_item):
        await create_item(name="Longsword", kind="WEAPON")
        await create_item(name="Leather Armor", kind="ARMOR")

        response = await client.get("/items")

        assert response.status_code == 200
        names = {item["name"] for item in response.json()["items"]}
        assert {"Longsword", "Leather Armor"} <= names

    async def test_list_items_filters_by_kind_subtype_rarity_and_magic(self, client, create_item):
        await create_item(name="Longsword", kind="WEAPON", rarity="NONE")
        await create_item(name="Cloak of Protection", kind="GEAR", subtype="WONDROUS_ITEM", rarity="UNCOMMON")

        weapons = await client.get("/items?kind=WEAPON")
        wondrous = await client.get("/items?subtype=WONDROUS_ITEM")
        uncommon = await client.get("/items?rarity=UNCOMMON")
        magic = await client.get("/items?magic=true")

        assert all(item["kind"] == "WEAPON" for item in weapons.json()["items"])
        for response in (wondrous, uncommon, magic):
            assert [item["name"] for item in response.json()["items"]] == ["Cloak of Protection"]

    async def test_list_rows_carry_the_kind_category(self, client, create_item):
        await create_item(name="Shield", kind="ARMOR", armor_category="SHIELD")

        row = (await client.get("/items?armor_category=SHIELD")).json()["items"][0]

        assert (row["name"], row["kind"], row["armor_category"]) == ("Shield", "ARMOR", "SHIELD")
        assert row["weapon_category"] is None

    async def test_get_item_by_id_with_its_details(self, client, create_item):
        item = await create_item(name="Longsword", kind="WEAPON", damage_dice_count=1, damage_dice_type="D8")

        response = await client.get(f"/items/{item.id}")

        assert response.status_code == 200
        body = response.json()
        assert (body["name"], body["kind"], body["armor"], body["tool"]) == ("Longsword", "WEAPON", None, None)
        assert (body["weapon"]["damage_dice_count"], body["weapon"]["damage_dice_type"]) == (1, "D8")

    async def test_get_item_404(self, client):
        assert (await client.get("/items/999999")).status_code == 404
