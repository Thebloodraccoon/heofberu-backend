"""Tests for the feature read endpoints."""

import pytest


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
        assert response.json()["name"] == "Extra Attack"

    async def test_get_feature_by_id(self, client, create_feature):
        feature = await create_feature(name="Extra Attack", source_type="OTHER")

        response = await client.get(f"/features/{feature.id}")

        assert response.status_code == 200
        assert response.json()["name"] == "Extra Attack"

    async def test_get_feature_404(self, client):
        assert (await client.get("/features/999999")).status_code == 404
