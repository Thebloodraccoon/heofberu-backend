"""
Class write behaviour: 422 instead of 500 for bad input, full-detail responses from every
sub-resource write, atomic PATCH, and exact cache invalidation (class reads vs. cached characters).
"""

import pytest

from app.core.cache.client import cache_prefix, cache_set


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def character_cache_key_exists(redis_client, character_id):
    return bool(await redis_client.exists(f"{cache_prefix()}:characters:{character_id}"))


@pytest.mark.integration
@pytest.mark.asyncio
class TestCreateValidation:
    @pytest.mark.parametrize(
        "extra",
        [
            {"name": ""},
            {"name": "x" * 101},
            {"skill_choice_count": -1},
            {"skill_choice_count": 99},
            {"image_url": "javascript:alert(1)"},
            {"image_url": "https://example.com/" + "a" * 600},
            {"description": "x" * 10_001},
        ],
    )
    async def test_invalid_create_returns_422(self, client, gm_token, extra):
        payload = {"name": "Fighter", "hit_dice": "D10", "spellcasting_ability": None, **extra}

        response = await client.post("/classes", json=payload, headers=auth(gm_token))

        assert response.status_code == 422

    async def test_valid_image_url_is_stored(self, client, gm_token):
        response = await client.post(
            "/classes",
            json={
                "name": "Fighter",
                "hit_dice": "D10",
                "spellcasting_ability": None,
                "image_url": "https://cdn.example.com/fighter.png",
            },
            headers=auth(gm_token),
        )

        assert response.status_code == 201
        assert response.json()["image_url"] == "https://cdn.example.com/fighter.png"


@pytest.mark.integration
@pytest.mark.asyncio
class TestPatchValidation:
    @pytest.mark.parametrize(
        "payload",
        [
            {"name": None},
            {"hit_dice": None},
            {"skill_choice_count": None},
            {"description": None},
            {"name": "x" * 101},
            {"name": ""},
            {"skill_choice_count": -1},
        ],
    )
    async def test_invalid_patch_returns_422_and_changes_nothing(self, client, gm_token, create_class, payload):
        character_class = await create_class(name="Fighter")

        response = await client.patch(f"/classes/{character_class.id}", json=payload, headers=auth(gm_token))

        assert response.status_code == 422
        assert (await client.get(f"/classes/{character_class.id}")).json()["name"] == "Fighter"

    async def test_spellcasting_ability_can_be_cleared(self, client, gm_token, create_class):
        character_class = await create_class(name="Wizard", spellcasting_ability="INT")

        response = await client.patch(
            f"/classes/{character_class.id}", json={"spellcasting_ability": None}, headers=auth(gm_token)
        )

        assert response.status_code == 200
        assert response.json()["spellcasting_ability"] is None

    async def test_duplicate_name_returns_400(self, client, gm_token, create_class):
        await create_class(name="Fighter")
        other = await create_class(name="Rogue")

        response = await client.patch(f"/classes/{other.id}", json={"name": "Fighter"}, headers=auth(gm_token))

        assert response.status_code == 400

    async def test_renaming_to_its_own_name_is_not_a_conflict(self, client, gm_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.patch(
            f"/classes/{character_class.id}", json={"name": "Fighter", "description": "d"}, headers=auth(gm_token)
        )

        assert response.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
class TestPatchIsAtomic:
    async def test_failed_rename_does_not_replace_saving_throws(self, client, gm_token, create_class):
        await create_class(name="Fighter")
        other_id = (await create_class(name="Rogue")).id
        await client.put(f"/classes/{other_id}/saving-throws", json={"saving_throws": ["DEX"]}, headers=auth(gm_token))

        response = await client.patch(
            f"/classes/{other_id}", json={"name": "Fighter", "saving_throws": ["STR", "CON"]}, headers=auth(gm_token)
        )

        assert response.status_code == 400
        fetched = (await client.get(f"/classes/{other_id}")).json()
        assert fetched["name"] == "Rogue"
        assert [t["ability"] for t in fetched["saving_throws"]] == ["DEX"]

    async def test_patch_updates_fields_and_saving_throws_together(self, client, gm_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.patch(
            f"/classes/{character_class.id}",
            json={"description": "Martial.", "saving_throws": ["STR", "CON"]},
            headers=auth(gm_token),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["description"] == "Martial."
        assert sorted(t["ability"] for t in body["saving_throws"]) == ["CON", "STR"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestSubResourceWritesReturnTheFullClass:
    async def test_put_responses_carry_features_and_subclasses_like_get(
        self, client, gm_token, create_class, create_subclass, create_feature, create_skill
    ):
        character_class = await create_class(name="Fighter")
        await create_subclass(class_id=character_class.id, name="Champion")
        await create_feature(name="Second Wind", source_type="CLASS", class_id=character_class.id, level=1)
        skill = await create_skill(name="Athletics", ability="STR")
        base = f"/classes/{character_class.id}"

        responses = [
            await client.put(f"{base}/saving-throws", json={"saving_throws": ["STR"]}, headers=auth(gm_token)),
            await client.put(
                f"{base}/armor-proficiencies", json={"armor_proficiencies": ["LIGHT"]}, headers=auth(gm_token)
            ),
            await client.put(
                f"{base}/weapon-proficiencies", json={"weapon_proficiencies": ["SIMPLE"]}, headers=auth(gm_token)
            ),
            await client.put(f"{base}/available-skills", json={"skill_ids": [skill.id]}, headers=auth(gm_token)),
            await client.put(f"{base}/items", json={"items": []}, headers=auth(gm_token)),
            await client.put(
                f"{base}/spell-slots",
                params={"class_level": 1},
                json={"slots": [{"spell_level": "LEVEL_1", "slots": 2}]},
                headers=auth(gm_token),
            ),
        ]

        for response in responses:
            assert response.status_code == 200, response.text
            body = response.json()
            assert [f["name"] for f in body["features"]] == ["Second Wind"]
            assert [s["name"] for s in body["subclasses"]] == ["Champion"]
        assert responses[-1].json() == (await client.get(base)).json()

    async def test_patch_response_carries_features_and_subclasses(
        self, client, gm_token, create_class, create_subclass, create_feature
    ):
        character_class = await create_class(name="Fighter")
        await create_subclass(class_id=character_class.id, name="Champion")
        await create_feature(name="Second Wind", source_type="CLASS", class_id=character_class.id, level=1)

        response = await client.patch(
            f"/classes/{character_class.id}", json={"description": "d"}, headers=auth(gm_token)
        )

        body = response.json()
        assert [f["name"] for f in body["features"]] == ["Second Wind"]
        assert [s["name"] for s in body["subclasses"]] == ["Champion"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestChoiceGroups:
    async def test_choice_groups_roundtrip_and_show_up_in_the_class(self, client, gm_token, create_class, create_item):
        character_class = await create_class(name="Bard")
        rapier = await create_item(name="Rapier")
        longsword = await create_item(name="Longsword")
        base = f"/classes/{character_class.id}"

        put = await client.put(
            f"{base}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "sort_order": 1,
                        "options": [{"item_id": rapier.id, "quantity": 1}, {"item_id": longsword.id, "quantity": 1}],
                    }
                ]
            },
            headers=auth(gm_token),
        )
        assert put.status_code == 200, put.text
        assert len(put.json()["choice_groups"]) == 1

        listed = await client.get(f"{base}/choice-groups")
        assert listed.status_code == 200
        group = listed.json()["choice_groups"][0]
        assert group["pick_count"] == 1
        assert {o["item"]["name"] for o in group["options"]} == {"Rapier", "Longsword"}

        detail = (await client.get(base)).json()
        assert len(detail["starting_choice_groups"]) == 1

        cleared = await client.put(f"{base}/choice-groups", json={"choice_groups": []}, headers=auth(gm_token))
        assert cleared.status_code == 200
        assert (await client.get(base)).json()["starting_choice_groups"] == []

    async def test_unknown_item_returns_400(self, client, gm_token, create_class):
        character_class = await create_class(name="Bard")

        response = await client.put(
            f"/classes/{character_class.id}/choice-groups",
            json={
                "choice_groups": [{"pick_count": 1, "sort_order": 1, "options": [{"item_id": 99999, "quantity": 1}]}]
            },
            headers=auth(gm_token),
        )

        assert response.status_code == 400

    async def test_player_cannot_replace_choice_groups(self, client, player_token, create_class):
        character_class = await create_class(name="Bard")

        response = await client.put(
            f"/classes/{character_class.id}/choice-groups", json={"choice_groups": []}, headers=auth(player_token)
        )

        assert response.status_code == 403

    async def test_choice_groups_of_unknown_class_return_404(self, client):
        assert (await client.get("/classes/999999/choice-groups")).status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestCacheInvalidation:
    async def test_class_read_is_fresh_after_every_kind_of_write(
        self, caching_on, client, gm_token, create_class, create_subclass
    ):
        class_id = (await create_class(name="Fighter")).id
        base = f"/classes/{class_id}"
        assert (await client.get(base)).json()["description"] == ""
        assert (await client.get("/classes")).json()["items"][0]["subclasses"] == []
        assert await caching_on.keys(f"{cache_prefix()}:classes:*")

        await client.patch(base, json={"description": "new"}, headers=auth(gm_token))
        assert (await client.get(base)).json()["description"] == "new"

        created = await client.post(
            "/subclasses", json={"name": "Champion", "class_id": class_id}, headers=auth(gm_token)
        )
        subclass_id = created.json()["id"]
        assert [s["name"] for s in (await client.get(base)).json()["subclasses"]] == ["Champion"]
        assert [s["name"] for s in (await client.get("/classes")).json()["items"][0]["subclasses"]] == ["Champion"]

        await client.patch(f"/subclasses/{subclass_id}", json={"name": "Battle Master"}, headers=auth(gm_token))
        assert [s["name"] for s in (await client.get(base)).json()["subclasses"]] == ["Battle Master"]
        assert (await client.get(f"/subclasses/{subclass_id}")).json()["name"] == "Battle Master"

    async def test_description_change_keeps_cached_characters_but_hit_dice_change_purges_only_its_own(
        self, caching_on, client, gm_token, create_class, create_user, create_character
    ):
        owner = await create_user(username="owner", email="owner@example.com")
        class_id = (await create_class(name="Fighter", hit_dice="D10")).id
        other_class_id = (await create_class(name="Rogue", hit_dice="D8")).id
        character_id = (await create_character(owner_id=owner.id, class_id=class_id)).id
        bystander_id = (await create_character(owner_id=owner.id, class_id=other_class_id, name="Bystander")).id
        for cached_id in (character_id, bystander_id):
            await cache_set(f"{cache_prefix()}:characters:{cached_id}", "{}")
        patch = f"/classes/{class_id}"

        await client.patch(patch, json={"description": "x"}, headers=auth(gm_token))
        assert await character_cache_key_exists(caching_on, character_id)

        await client.patch(patch, json={"hit_dice": "D10"}, headers=auth(gm_token))
        assert await character_cache_key_exists(caching_on, character_id)

        response = await client.patch(patch, json={"hit_dice": "D12"}, headers=auth(gm_token))
        assert response.status_code == 200
        assert not await character_cache_key_exists(caching_on, character_id)
        assert await character_cache_key_exists(caching_on, bystander_id)

    async def test_deleting_a_class_drops_its_cached_reads(self, caching_on, client, founder_token, create_class):
        class_id = (await create_class(name="Doomed")).id
        base = f"/classes/{class_id}"
        for path in (base, f"{base}/features", f"{base}/progression"):
            assert (await client.get(path)).status_code == 200

        assert (await client.delete(base, headers=auth(founder_token))).status_code == 204

        for path in (base, f"{base}/features", f"{base}/progression"):
            assert (await client.get(path)).status_code == 404
