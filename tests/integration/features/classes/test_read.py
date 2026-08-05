"""Tests for the class read endpoints."""

import pytest


@pytest.mark.integration
class TestClassOpenRead:
    def test_list_classes(self, client, create_class):
        create_class(name="Fighter", hit_dice="D10")
        create_class(name="Wizard", hit_dice="D6", spellcasting_ability="INT")

        response = client.get("/classes/")

        assert response.status_code == 200
        names = {item["name"] for item in response.json()["items"]}
        assert {"Fighter", "Wizard"} <= names

    def test_list_classes_search(self, client, create_class):
        create_class(name="Bard", hit_dice="D8")
        create_class(name="Rogue", hit_dice="D8")

        response = client.get("/classes/?search=bar")

        assert response.status_code == 200
        names = [item["name"] for item in response.json()["items"]]
        assert names == ["Bard"]

    def test_get_class_by_id(self, client, create_class):
        character_class = create_class(name="Cleric", hit_dice="D8", spellcasting_ability="WIS")

        response = client.get(f"/classes/{character_class.id}")

        assert response.status_code == 200
        assert response.json()["name"] == "Cleric"
        assert response.json()["spellcasting_ability"] == "WIS"

    def test_get_class_404(self, client):
        assert client.get("/classes/999999").status_code == 404
