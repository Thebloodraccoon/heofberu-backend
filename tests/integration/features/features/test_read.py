"""Tests for the feature read endpoints."""

import pytest

from tests.helpers import set_choice_groups


@pytest.mark.integration
@pytest.mark.asyncio
class TestFeatureOpenRead:
    async def test_list_features(self, client, create_feature):
        await create_feature(name="Extra Attack", source_type="OTHER")
        await create_feature(name="Darkvision", source_type="OTHER")

        response = await client.get("/features")

        assert response.status_code == 200
        names = {item["name"] for item in response.json()["items"]}
        assert {"Extra Attack", "Darkvision"} <= names

    async def test_list_features_excludes_source_owned_features(self, client, create_class, create_feature):
        character_class = await create_class(name="Fighter")
        await create_feature(name="Extra Attack", source_type="CLASS", class_id=character_class.id, level=5)
        await create_feature(name="Homebrew Boon", source_type="OTHER")

        response = await client.get("/features")

        assert response.status_code == 200
        names = {item["name"] for item in response.json()["items"]}
        assert "Homebrew Boon" in names
        assert "Extra Attack" not in names

    async def test_get_source_owned_feature_by_id(self, client, create_class, create_feature):
        character_class = await create_class(name="Fighter")
        feature = await create_feature(name="Extra Attack", source_type="CLASS", class_id=character_class.id, level=5)

        response = await client.get(f"/features/{feature.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Extra Attack"
        assert body["choice_groups"] == []
        assert body["static_groups"] == []
        assert body["has_static_effects"] is False
        assert body["has_choices"] is False

    async def test_get_feature_by_id(self, client, create_feature):
        feature = await create_feature(name="Extra Attack", source_type="OTHER")

        response = await client.get(f"/features/{feature.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Extra Attack"
        assert body["static_groups"] == []
        assert body["choice_groups"] == []

    async def test_get_feature_404(self, client):
        assert (await client.get("/features/999999")).status_code == 404

    async def test_get_feature_names_the_classes_of_an_open_spell_filter(
        self, client, gm_token, create_class, create_feature
    ):
        bard = await create_class(name="Bard")
        cleric = await create_class(name="Cleric")
        feature = await create_feature(name="Any Caster Spell", source_type="OTHER")
        option = {"effects": [{"effect_type": "spell", "items": [{"class_ids": [cleric.id, bard.id]}]}]}
        groups = {"choice_groups": [{"pick_count": 1, "choice_type": "SPELL", "options": [option]}]}
        assert (await set_choice_groups(client, gm_token, feature.id, groups)).status_code == 200

        response = await client.get(f"/features/{feature.id}")

        assert response.status_code == 200
        body = response.json()
        (spell_group,) = body["choice_groups"][0]["options"][0]["effects"]
        assert spell_group["items"][0]["summary"] == ["из списка: Bard, Cleric"]
        assert "из списка: Bard, Cleric" in body["effects_summary"]
