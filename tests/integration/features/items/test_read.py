"""Tests for the item read endpoints."""

import pytest


@pytest.mark.integration
class TestItemOpenRead:
    def test_list_items(self, client, create_item):
        create_item(name="Longsword", item_type="WEAPON")
        create_item(name="Leather Armor", item_type="ARMOR")

        response = client.get("/items/")

        assert response.status_code == 200
        names = {item["name"] for item in response.json()["items"]}
        assert {"Longsword", "Leather Armor"} <= names

    def test_list_items_filters_by_type_and_rarity(self, client, create_item):
        create_item(name="Longsword", item_type="WEAPON", rarity="NONE")
        create_item(name="Cloak of Protection", item_type="WONDROUS_ITEM", rarity="UNCOMMON")

        response = client.get("/items/?item_type=WEAPON")

        assert response.status_code == 200
        assert all(item["item_type"] == "WEAPON" for item in response.json()["items"])

        rarity_response = client.get("/items/?rarity=UNCOMMON")
        assert [item["name"] for item in rarity_response.json()["items"]] == ["Cloak of Protection"]

    def test_get_item_by_id(self, client, create_item):
        item = create_item(name="Longsword", item_type="WEAPON")

        response = client.get(f"/items/{item.id}")

        assert response.status_code == 200
        assert response.json()["name"] == "Longsword"

    def test_get_item_404(self, client):
        assert client.get("/items/999999").status_code == 404
