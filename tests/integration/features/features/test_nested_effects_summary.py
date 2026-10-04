"""
``has_static_effects``/``has_choices``/``effects_summary`` on features
embedded inside a parent catalog response (``NestedFeatureResponse``), and
the cache-invalidation fix that keeps those parent reads from going stale
after ``PUT /features/{id}/effects`` or ``PUT /features/{id}/choice-groups``
(FeatureEffectsService used to only purge the shared ``features`` namespace,
never the owning catalog's own list/parent-read namespaces).
"""

import pytest


async def set_feature_effects(client, gm_token, feature_id, **effects):
    """``skill_effects=[...]`` style kwargs, sent as ``static_groups``."""

    static_groups = [{"effect_type": key.removesuffix("_effects"), "items": items} for key, items in effects.items()]
    response = await client.put(
        f"/features/{feature_id}/effects",
        json={"static_groups": static_groups},
        headers={"Authorization": f"Bearer {gm_token}"},
    )
    assert response.status_code == 200, response.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestNestedFeatureSummary:
    async def test_background_response_embeds_summary_and_flags(
        self, client, gm_token, create_background, create_feature, create_skill
    ):
        background = await create_background(name="Sage", with_suggestions=False)
        skill = await create_skill(name="Arcana", ability="INT")
        feature = await create_feature(name="Researcher", source_type="BACKGROUND", background_id=background.id)

        await set_feature_effects(client, gm_token, feature.id, skill_effects=[{"skill_id": skill.id}])

        detail = await client.get(f"/backgrounds/{background.id}", headers={"Authorization": f"Bearer {gm_token}"})
        assert detail.status_code == 200
        nested = next(f for f in detail.json()["features"] if f["id"] == feature.id)
        assert nested["has_static_effects"] is True
        assert nested["has_choices"] is False
        assert "Arcana" in nested["effects_summary"]

        listing = await client.get(
            f"/backgrounds/{background.id}/features", headers={"Authorization": f"Bearer {gm_token}"}
        )
        assert listing.status_code == 200
        listed = next(f for f in listing.json() if f["id"] == feature.id)
        assert listed["has_static_effects"] is True
        assert "Arcana" in listed["effects_summary"]

    async def test_race_response_embeds_choice_group_flag(self, client, gm_token, create_race, create_feature):
        race = await create_race(name="Draconic")
        feature = await create_feature(name="Ancestry", source_type="RACE", race_id=race.id)

        cg_resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "ABILITY_SCORE",
                        "label": "Choose an ability",
                        "options": [
                            {"effects": [{"effect_type": "ability", "items": [{"ability": "STR", "amount": 1}]}]},
                            {"effects": [{"effect_type": "ability", "items": [{"ability": "DEX", "amount": 1}]}]},
                        ],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert cg_resp.status_code == 200

        detail = await client.get(f"/races/{race.id}", headers={"Authorization": f"Bearer {gm_token}"})
        assert detail.status_code == 200
        nested = next(f for f in detail.json()["features"] if f["id"] == feature.id)
        assert nested["has_choices"] is True
        assert nested["has_static_effects"] is False
        assert "Сила" in nested["effects_summary"]
        assert "Ловкость" in nested["effects_summary"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestParentCacheInvalidatedByEffectsEdit:
    async def test_background_detail_cache_reflects_effects_edit(
        self, client, gm_token, create_background, create_feature, create_skill
    ):
        background = await create_background(name="Hermit", with_suggestions=False)
        skill_a = await create_skill(name="Medicine", ability="WIS")
        skill_b = await create_skill(name="Religion", ability="INT")
        feature = await create_feature(name="Discovery", source_type="BACKGROUND", background_id=background.id)

        await set_feature_effects(client, gm_token, feature.id, skill_effects=[{"skill_id": skill_a.id}])

        # Warm the cached detail read.
        first = await client.get(f"/backgrounds/{background.id}", headers={"Authorization": f"Bearer {gm_token}"})
        assert first.status_code == 200
        first_nested = next(f for f in first.json()["features"] if f["id"] == feature.id)
        assert "Medicine" in first_nested["effects_summary"]

        await set_feature_effects(client, gm_token, feature.id, skill_effects=[{"skill_id": skill_b.id}])

        second = await client.get(f"/backgrounds/{background.id}", headers={"Authorization": f"Bearer {gm_token}"})
        assert second.status_code == 200
        second_nested = next(f for f in second.json()["features"] if f["id"] == feature.id)
        assert "Religion" in second_nested["effects_summary"]
        assert "Medicine" not in second_nested["effects_summary"]

    async def test_background_feature_list_cache_reflects_choice_groups_edit(
        self, client, gm_token, create_background, create_feature
    ):
        background = await create_background(name="Wanderer", with_suggestions=False)
        feature = await create_feature(name="Wayfinder", source_type="BACKGROUND", background_id=background.id)

        # Warm the cached feature-list read (no choice groups yet).
        first = await client.get(
            f"/backgrounds/{background.id}/features", headers={"Authorization": f"Bearer {gm_token}"}
        )
        assert first.status_code == 200
        first_listed = next(f for f in first.json() if f["id"] == feature.id)
        assert first_listed["has_choices"] is False

        await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "SAVING_THROW",
                        "label": "Direction",
                        "options": [{"effects": [{"effect_type": "saving_throw", "items": [{"ability": "WIS"}]}]}],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        second = await client.get(
            f"/backgrounds/{background.id}/features", headers={"Authorization": f"Bearer {gm_token}"}
        )
        assert second.status_code == 200
        second_listed = next(f for f in second.json() if f["id"] == feature.id)
        assert second_listed["has_choices"] is True
