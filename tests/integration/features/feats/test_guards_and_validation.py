"""Feat validation, name uniqueness, delete guard, effects-router scoping and cache invalidation."""

import pytest

from app.settings import settings
from tests.helpers import set_effects


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
@pytest.mark.asyncio
class TestCreateValidation:
    async def test_documented_prerequisite_example_is_valid(self, client, gm_token):
        response = await client.post(
            "/feats",
            json={
                "name": "Heavy Armor Master",
                "prerequisite_ability": "STR",
                "prerequisite_minimum_score": 13,
                "description": "Damage reduction while in heavy armor.",
            },
            headers=auth(gm_token),
        )

        assert response.status_code == 201
        body = response.json()
        assert (body["prerequisite_ability"], body["prerequisite_minimum_score"]) == ("STR", 13)

    async def test_create_without_name_returns_422(self, client, gm_token):
        response = await client.post("/feats", json={"description": "No name"}, headers=auth(gm_token))

        assert response.status_code == 422

    @pytest.mark.parametrize("name", ["", "   ", "x" * 201])
    async def test_create_rejects_bad_names(self, client, gm_token, name):
        response = await client.post("/feats", json={"name": name}, headers=auth(gm_token))

        assert response.status_code == 422

    @pytest.mark.parametrize(
        "payload",
        [
            {"prerequisite_ability": "STR"},
            {"prerequisite_minimum_score": 13},
        ],
    )
    async def test_create_requires_prerequisite_pair(self, client, gm_token, payload):
        response = await client.post("/feats", json={"name": "Half Prereq", **payload}, headers=auth(gm_token))

        assert response.status_code == 422

    @pytest.mark.parametrize("score", [0, 31, 2**40])
    async def test_create_rejects_out_of_range_prerequisite_score(self, client, gm_token, score):
        response = await client.post(
            "/feats",
            json={"name": "Bad Score", "prerequisite_ability": "STR", "prerequisite_minimum_score": score},
            headers=auth(gm_token),
        )

        assert response.status_code == 422

    async def test_create_rejects_out_of_range_asi_amount(self, client, gm_token):
        response = await client.post(
            "/feats",
            json={"name": "Huge", "ability_score_increases": [{"ability": "STR", "amount": 2**40}]},
            headers=auth(gm_token),
        )

        assert response.status_code == 422

    async def test_create_with_asi_choice_builds_one_choice_group(self, client, gm_token):
        response = await client.post(
            "/feats",
            json={
                "name": "Resilient",
                "ability_score_increases": [{"ability": "STR", "amount": 1}, {"ability": "DEX", "amount": 1}],
            },
            headers=auth(gm_token),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["has_choices"] is True
        assert len(body["choice_groups"]) == 1
        assert len(body["choice_groups"][0]["options"]) == 2


@pytest.mark.integration
@pytest.mark.asyncio
class TestUpdate:
    async def test_patch_to_existing_name_returns_409(self, client, gm_token, create_feat):
        await create_feat(name="Alert")
        other = await create_feat(name="Lucky")

        response = await client.patch(f"/feats/{other.id}", json={"name": "Alert"}, headers=auth(gm_token))

        assert response.status_code == 409

    async def test_patch_keeping_own_name_is_fine(self, client, gm_token, create_feat):
        feat = await create_feat(name="Alert")

        response = await client.patch(
            f"/feats/{feat.id}", json={"name": "Alert", "description": "Updated."}, headers=auth(gm_token)
        )

        assert response.status_code == 200
        assert response.json()["description"] == "Updated."

    @pytest.mark.parametrize("field", ["name", "description", "prerequisite_description"])
    async def test_patch_rejects_explicit_null(self, client, gm_token, create_feat, field):
        feat = await create_feat(name="Alert")

        response = await client.patch(f"/feats/{feat.id}", json={field: None}, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_patch_setting_only_ability_returns_422(self, client, gm_token, create_feat):
        feat = await create_feat(name="Alert")

        response = await client.patch(f"/feats/{feat.id}", json={"prerequisite_ability": "STR"}, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_patch_can_set_and_clear_the_prerequisite_pair(self, client, gm_token, create_feat):
        feat = await create_feat(name="Alert")
        path = f"/feats/{feat.id}"

        set_response = await client.patch(
            path, json={"prerequisite_ability": "STR", "prerequisite_minimum_score": 13}, headers=auth(gm_token)
        )
        assert set_response.status_code == 200

        clear_response = await client.patch(
            path, json={"prerequisite_ability": None, "prerequisite_minimum_score": None}, headers=auth(gm_token)
        )
        assert clear_response.status_code == 200
        assert clear_response.json()["prerequisite_ability"] is None

    async def test_patch_response_keeps_the_effect_tree(self, client, gm_token, create_feat):
        created = await client.post(
            "/feats",
            json={"name": "Resilient", "ability_score_increases": [{"ability": "STR", "amount": 1}]},
            headers=auth(gm_token),
        )
        feat_id = created.json()["id"]

        response = await client.patch(f"/feats/{feat_id}", json={"description": "New."}, headers=auth(gm_token))

        assert response.status_code == 200
        assert response.json()["has_choices"] is True
        assert len(response.json()["choice_groups"]) == 1

    async def test_patch_of_a_non_feat_feature_returns_404(self, client, gm_token, create_class, create_feature):
        fighter = await create_class(name="Fighter")
        feature = await create_feature(name="Second Wind", source_type="CLASS", class_id=fighter.id)

        response = await client.patch(f"/feats/{feature.id}", json={"name": "Hijacked"}, headers=auth(gm_token))

        assert response.status_code == 404

    async def test_patch_missing_feat_returns_404(self, client, gm_token):
        response = await client.patch("/feats/999999", json={"name": "Nope"}, headers=auth(gm_token))

        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestDelete:
    async def test_delete_blocked_when_granted_to_several_characters(
        self, client, founder_token, gm_token, player, create_class, create_character, create_feat
    ):
        feat = await create_feat(name="Popular Feat")
        fighter = await create_class(name="Fighter")
        feat_id = feat.id

        for _ in range(2):
            character = await create_character(owner_id=player.id, class_id=fighter.id)
            added = await client.post(
                f"/characters/{character.id}/gm-panel/feats", json={"feat_id": feat_id}, headers=auth(gm_token)
            )
            assert added.status_code == 201

        response = await client.delete(f"/feats/{feat_id}", headers=auth(founder_token))

        assert response.status_code == 409
        assert (await client.get(f"/feats/{feat_id}")).status_code == 200

    async def test_delete_of_a_non_feat_feature_returns_404(self, client, founder_token, create_class, create_feature):
        fighter = await create_class(name="Fighter")
        feature = await create_feature(name="Second Wind", source_type="CLASS", class_id=fighter.id)
        feature_id = feature.id

        response = await client.delete(f"/feats/{feature_id}", headers=auth(founder_token))

        assert response.status_code == 404
        assert (await client.get(f"/features/{feature_id}")).status_code == 200

    async def test_delete_feat_with_effects_removes_them(self, client, founder_token, gm_token):
        created = await client.post(
            "/feats",
            json={"name": "Resilient", "ability_score_increases": [{"ability": "STR", "amount": 1}]},
            headers=auth(gm_token),
        )
        feat_id = created.json()["id"]

        assert (await client.delete(f"/feats/{feat_id}", headers=auth(founder_token))).status_code == 204
        assert (await client.get(f"/feats/{feat_id}")).status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestEffectsMountIsScopedToFeats:
    async def test_effects_of_a_feat_are_readable(self, client, create_feat):
        feat = await create_feat(name="Alert")

        response = await client.get(f"/feats/{feat.id}/effects")

        assert response.status_code == 200

    async def test_effects_of_a_class_feature_are_not_reachable_through_feats(
        self, client, gm_token, create_class, create_feature
    ):
        fighter = await create_class(name="Fighter")
        feature = await create_feature(name="Second Wind", source_type="CLASS", class_id=fighter.id)

        read = await client.get(f"/feats/{feature.id}/effects")
        write = await set_effects(
            client,
            gm_token,
            feature.id,
            {"static_groups": [{"effect_type": "ability", "items": [{"ability": "STR", "amount": 1}]}]},
            base="/feats",
        )

        assert read.status_code == 404
        assert write.status_code == 404
        assert (await client.get(f"/features/{feature.id}/effects")).status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
class TestCacheInvalidation:
    async def test_patch_refreshes_cached_reads(self, client, gm_token, create_feat, redis_client, monkeypatch):
        monkeypatch.setattr(settings, "CACHE_ENABLED", True)
        feat = await create_feat(name="Old Name")
        feat_id = feat.id

        assert (await client.get(f"/feats/{feat_id}")).json()["name"] == "Old Name"
        assert "Old Name" in {item["name"] for item in (await client.get("/feats")).json()["items"]}
        assert (await client.get("/features")).status_code == 200

        await client.patch(f"/feats/{feat_id}", json={"name": "New Name"}, headers=auth(gm_token))

        assert (await client.get(f"/feats/{feat_id}")).json()["name"] == "New Name"
        assert "New Name" in {item["name"] for item in (await client.get("/feats")).json()["items"]}

    async def test_skill_rename_refreshes_feat_effects_summary(
        self, client, gm_token, create_feat, create_skill, redis_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "CACHE_ENABLED", True)
        feat = await create_feat(name="Skilled")
        skill = await create_skill(name="Stealth", ability="DEX")
        feat_id, skill_id = feat.id, skill.id
        put = await set_effects(
            client,
            gm_token,
            feat_id,
            {"static_groups": [{"effect_type": "skill", "items": [{"skill_id": skill_id}]}]},
            base="/feats",
        )
        assert put.status_code == 200

        assert "Stealth" in (await client.get(f"/feats/{feat_id}")).json()["effects_summary"]

        await client.patch(f"/skills/{skill_id}", json={"name": "Sneaking"}, headers=auth(gm_token))

        assert "Sneaking" in (await client.get(f"/feats/{feat_id}")).json()["effects_summary"]
        assert "Sneaking" in (await client.get(f"/features/{feat_id}")).json()["effects_summary"]
