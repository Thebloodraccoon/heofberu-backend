"""Tests for the feat read endpoints."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestFeatOpenRead:
    async def test_list_feats(self, client, create_feat):
        await create_feat(name="Alert")
        await create_feat(name="Lucky")

        response = await client.get("/feats")

        assert response.status_code == 200
        names = {item["name"] for item in response.json()["items"]}
        assert {"Alert", "Lucky"} <= names

    async def test_get_feat_by_id(self, client, create_feat):
        feat = await create_feat(name="Alert")

        response = await client.get(f"/feats/{feat.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Alert"
        assert body["ability_score_increases"] == []
        assert body["choice_groups"] == []
        assert body["skill_effects"] == []
        assert body["saving_throw_effects"] == []
        assert body["armor_effects"] == []
        assert body["weapon_effects"] == []
        assert body["spell_effects"] == []

    async def test_get_feat_404(self, client):
        assert (await client.get("/feats/999999")).status_code == 404
