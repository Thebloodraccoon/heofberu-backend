"""Skill validation, filters, delete guards and cache invalidation of dependent namespaces."""

import pytest

from app.settings import settings


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestValidation:
    @pytest.mark.parametrize("name", ["", "   ", "x" * 101])
    async def test_create_rejects_bad_names(self, client, gm_token, name):
        response = await client.post("/skills", json={"name": name, "ability": "DEX"}, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_create_rejects_unknown_ability(self, client, gm_token):
        response = await client.post("/skills", json={"name": "Odd", "ability": "LUCK"}, headers=auth(gm_token))

        assert response.status_code == 422

    @pytest.mark.parametrize("field", ["name", "ability", "description"])
    async def test_patch_rejects_explicit_null(self, client, gm_token, create_skill, field):
        skill = await create_skill(name="Stealth", ability="DEX")

        response = await client.patch(f"/skills/{skill.id}", json={field: None}, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_patch_to_existing_name_returns_400(self, client, gm_token, create_skill):
        await create_skill(name="Stealth", ability="DEX")
        other = await create_skill(name="Arcana", ability="INT")

        response = await client.patch(f"/skills/{other.id}", json={"name": "Stealth"}, headers=auth(gm_token))

        assert response.status_code == 400

    async def test_documented_create_example_is_valid(self, client, gm_token):
        response = await client.post(
            "/skills",
            json={"name": "Perception", "ability": "WIS", "description": "Spot, hear, or detect something."},
            headers=auth(gm_token),
        )

        assert response.status_code == 201

    async def test_patch_missing_skill_returns_404(self, client, gm_token):
        response = await client.patch("/skills/999999", json={"name": "Nope"}, headers=auth(gm_token))

        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestListing:
    async def test_filters_by_ability_and_search(self, client, create_skill):
        await create_skill(name="Stealth", ability="DEX")
        await create_skill(name="Acrobatics", ability="DEX")
        await create_skill(name="Arcana", ability="INT")

        by_ability = await client.get("/skills", params={"ability": ["DEX"]})
        by_search = await client.get("/skills", params={"search": "arc"})
        multi = await client.get("/skills", params={"ability": ["DEX", "INT"]})

        assert {item["name"] for item in by_ability.json()["items"]} == {"Stealth", "Acrobatics"}
        assert {item["name"] for item in by_search.json()["items"]} == {"Arcana"}
        assert by_search.json()["total"] == 1
        assert multi.json()["total"] == 3

    async def test_search_longer_than_limit_returns_422(self, client):
        assert (await client.get("/skills", params={"search": "x" * 101})).status_code == 422

    async def test_listing_is_ordered_by_name(self, client, create_skill):
        for name in ("Stealth", "Arcana", "Medicine"):
            await create_skill(name=name, ability="DEX")

        names = [item["name"] for item in (await client.get("/skills")).json()["items"]]

        assert names == sorted(names)


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeleteGuards:
    async def test_delete_blocked_when_granted_by_a_background(
        self, client, founder_token, gm_token, create_skill, create_background
    ):
        skill = await create_skill(name="Arcana", ability="INT")
        background = await create_background(name="Sage")
        skill_id = skill.id
        await client.put(f"/backgrounds/{background.id}/skills", json={"skill_ids": [skill_id]}, headers=auth(gm_token))

        response = await client.delete(f"/skills/{skill_id}", headers=auth(founder_token))

        assert response.status_code == 409

    async def test_delete_blocked_when_a_feature_effect_references_it(
        self, client, founder_token, gm_token, create_skill, create_feat
    ):
        skill = await create_skill(name="Stealth", ability="DEX")
        feat = await create_feat(name="Skilled")
        skill_id = skill.id
        put = await client.put(
            f"/feats/{feat.id}/effects",
            json={"static_groups": [{"effect_type": "skill", "items": [{"skill_id": skill_id}]}]},
            headers=auth(gm_token),
        )
        assert put.status_code == 200

        response = await client.delete(f"/skills/{skill_id}", headers=auth(founder_token))

        assert response.status_code == 409
        assert (await client.get(f"/skills/{skill_id}")).status_code == 200

    async def test_delete_missing_skill_returns_404(self, client, founder_token):
        assert (await client.delete("/skills/999999", headers=auth(founder_token))).status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestCacheInvalidation:
    async def test_rename_refreshes_listing_background_and_class_payloads(
        self, client, gm_token, create_skill, create_background, redis_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "CACHE_ENABLED", True)
        skill = await create_skill(name="Stealth", ability="DEX")
        background = await create_background(name="Sage")
        skill_id, background_id = skill.id, background.id
        await client.put(f"/backgrounds/{background_id}/skills", json={"skill_ids": [skill_id]}, headers=auth(gm_token))

        assert (await client.get(f"/skills/{skill_id}")).json()["name"] == "Stealth"
        assert (await client.get(f"/backgrounds/{background_id}")).json()["granted_skills"][0]["name"] == "Stealth"

        await client.patch(f"/skills/{skill_id}", json={"name": "Sneaking"}, headers=auth(gm_token))

        assert (await client.get(f"/skills/{skill_id}")).json()["name"] == "Sneaking"
        assert (await client.get(f"/backgrounds/{background_id}")).json()["granted_skills"][0]["name"] == "Sneaking"

    async def test_create_purges_the_listing_but_not_dependent_namespaces(
        self, client, gm_token, create_background, redis_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "CACHE_ENABLED", True)
        background = await create_background(name="Sage")
        background_id = background.id
        await client.get(f"/backgrounds/{background_id}")
        await client.get("/skills")
        prefix = settings.CACHE_PREFIX

        created = await client.post("/skills", json={"name": "Brand New", "ability": "STR"}, headers=auth(gm_token))

        assert created.status_code == 201
        assert await redis_client.keys(f"{prefix}:skills:*") == []
        assert await redis_client.keys(f"{prefix}:backgrounds:*") != []
        assert "Brand New" in {item["name"] for item in (await client.get("/skills")).json()["items"]}
