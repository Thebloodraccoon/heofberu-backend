"""Tests for the class read endpoints."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestClassOpenRead:
    async def test_list_classes(self, client, create_class):
        await create_class(name="Fighter", hit_dice="D10")
        await create_class(name="Wizard", hit_dice="D6", spellcasting_ability="INT")

        response = await client.get("/classes/")

        assert response.status_code == 200
        names = {item["name"] for item in response.json()["items"]}
        assert {"Fighter", "Wizard"} <= names

    async def test_list_classes_search(self, client, create_class):
        await create_class(name="Bard", hit_dice="D8")
        await create_class(name="Rogue", hit_dice="D8")

        response = await client.get("/classes/?search=bar")

        assert response.status_code == 200
        names = [item["name"] for item in response.json()["items"]]
        assert names == ["Bard"]

    async def test_get_class_by_id(self, client, create_class):
        character_class = await create_class(name="Cleric", hit_dice="D8", spellcasting_ability="WIS")

        response = await client.get(f"/classes/{character_class.id}")

        assert response.status_code == 200
        assert response.json()["name"] == "Cleric"
        assert response.json()["spellcasting_ability"] == "WIS"

    async def test_get_class_404(self, client):
        assert (await client.get("/classes/999999")).status_code == 404

    async def test_list_subclasses(self, client, create_class, create_subclass):
        character_class = await create_class(name="Fighter")
        await create_subclass(class_id=character_class.id, name="Battle Master")
        await create_subclass(class_id=character_class.id, name="Champion")

        response = await client.get(f"/classes/{character_class.id}/subclasses")

        assert response.status_code == 200
        assert {item["name"] for item in response.json()} == {"Battle Master", "Champion"}

    async def test_get_subclass_includes_features(self, client, create_class, create_subclass, create_feature):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")
        await create_feature(name="Improved Critical", source_type="SUBCLASS", subclass_id=subclass.id, level=3)

        response = await client.get(f"/classes/{character_class.id}/subclasses/{subclass.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Champion"
        assert body["unlock_level"] == 3
        assert [item["name"] for item in body["features"]] == ["Improved Critical"]

    async def test_get_subclass_404(self, client, create_class):
        character_class = await create_class(name="Fighter")

        assert (
            await client.get(f"/classes/{character_class.id}/subclasses/999999")
        ).status_code == 404
