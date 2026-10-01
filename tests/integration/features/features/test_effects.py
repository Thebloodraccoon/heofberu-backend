"""Tests for the feature effects endpoints: GET/PUT /features/{id}/effects and choice-groups."""

import pytest


async def set_effects(client, gm_token, feature_id, payload):
    return await client.put(
        f"/features/{feature_id}/effects",
        json=payload,
        headers={"Authorization": f"Bearer {gm_token}"},
    )


def static_items(body, effect_type):
    """Pull the ``items`` list of one ``effect_type`` group out of a ``static_groups`` response, or ``[]``."""

    return next((g["items"] for g in body["static_groups"] if g["effect_type"] == effect_type), [])


@pytest.mark.integration
@pytest.mark.asyncio
class TestFeatureEffectsCrud:
    async def test_empty_by_default(self, client, gm_token, create_feature):
        feature = await create_feature(name="Plain Feature")

        response = await client.get(f"/features/{feature.id}/effects")

        assert response.status_code == 200
        body = response.json()
        assert body["feature_id"] == feature.id
        assert body["static_groups"] == []
        assert body["choice_groups"] == []

    async def test_gm_can_set_ability_effects(self, client, gm_token, create_feature):
        feature = await create_feature(name="Primal Champion")

        response = await set_effects(
            client,
            gm_token,
            feature.id,
            {"ability_effects": [{"ability": "STR", "amount": 4, "new_cap": 24}, {"ability": "CON", "amount": 4}]},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["feature_id"] == feature.id
        abilities = static_items(body, "ability")
        assert {item["ability"]: item["amount"] for item in abilities} == {"STR": 4, "CON": 4}
        assert next(item for item in abilities if item["ability"] == "STR")["new_cap"] == 24

    async def test_dropping_an_item_from_the_payload_deletes_it(self, client, gm_token, create_feature):
        feature = await create_feature(name="Shifting Effect")
        await set_effects(
            client,
            gm_token,
            feature.id,
            {"ability_effects": [{"ability": "STR", "amount": 2}, {"ability": "DEX", "amount": 1}]},
        )

        response = await set_effects(
            client, gm_token, feature.id, {"ability_effects": [{"ability": "CHA", "amount": -2}]}
        )

        assert response.status_code == 200
        abilities = {item["ability"] for item in static_items(response.json(), "ability")}
        assert abilities == {"CHA"}

    async def test_passing_the_id_back_updates_the_same_row_in_place(self, client, gm_token, create_feature):
        feature = await create_feature(name="In-Place Edit")
        first = await set_effects(client, gm_token, feature.id, {"ability_effects": [{"ability": "STR", "amount": 1}]})
        row_id = static_items(first.json(), "ability")[0]["id"]

        response = await set_effects(
            client, gm_token, feature.id, {"ability_effects": [{"id": row_id, "ability": "STR", "amount": 5}]}
        )

        assert response.status_code == 200
        abilities = static_items(response.json(), "ability")
        assert len(abilities) == 1
        assert abilities[0]["id"] == row_id
        assert abilities[0]["amount"] == 5

    async def test_foreign_id_returns_422(self, client, gm_token, create_feature):
        feature_a = await create_feature(name="Owner A")
        feature_b = await create_feature(name="Owner B")
        set_a = await set_effects(
            client, gm_token, feature_a.id, {"ability_effects": [{"ability": "STR", "amount": 1}]}
        )
        stray_id = static_items(set_a.json(), "ability")[0]["id"]

        response = await set_effects(
            client, gm_token, feature_b.id, {"ability_effects": [{"id": stray_id, "ability": "DEX", "amount": 1}]}
        )

        assert response.status_code == 422

    async def test_clear_with_empty_list(self, client, gm_token, create_feature):
        feature = await create_feature(name="Temporary Effect")
        await set_effects(client, gm_token, feature.id, {"ability_effects": [{"ability": "WIS", "amount": 1}]})

        response = await set_effects(client, gm_token, feature.id, {"ability_effects": []})

        assert response.status_code == 200
        assert static_items(response.json(), "ability") == []

    async def test_duplicate_ability_returns_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Dup Effect")

        response = await set_effects(
            client,
            gm_token,
            feature.id,
            {"ability_effects": [{"ability": "STR", "amount": 1}, {"ability": "STR", "amount": 1}]},
        )

        assert response.status_code == 422

    async def test_unknown_feature_returns_404(self, client, gm_token):
        response = await set_effects(client, gm_token, 999999, {"ability_effects": []})

        assert response.status_code == 404

    async def test_player_cannot_write(self, client, player_token, create_feature):
        feature = await create_feature(name="Player Proof")

        response = await set_effects(
            client, player_token, feature.id, {"ability_effects": [{"ability": "STR", "amount": 1}]}
        )

        assert response.status_code == 403

    async def test_read_is_open(self, client, create_feature):
        feature = await create_feature(name="Open Read")

        response = await client.get(f"/features/{feature.id}/effects")

        assert response.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
class TestFeatureEffectsAllTypes:
    async def test_put_all_six_effect_types(
        self, client, gm_token, create_feature, create_skill, create_item, create_spell
    ):
        feature = await create_feature(name="Epic Feature", source_type="CLASS", level=None)
        skill = await create_skill(name="Stealth", ability="DEX")
        await create_item(name="Longsword", item_type="WEAPON")
        spell = await create_spell(name="Fireball", school="EVOCATION", level="LEVEL_3")

        response = await set_effects(
            client,
            gm_token,
            feature.id,
            {
                "ability_effects": [{"ability": "STR", "amount": 2}],
                "skill_effects": [{"skill_id": skill.id}],
                "saving_throw_effects": [{"ability": "DEX"}],
                "armor_effects": [{"armor_type": "LIGHT"}],
                "weapon_effects": [{"weapon_category": "MARTIAL"}],
                "spell_effects": [{"spell_id": spell.id}],
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert static_items(body, "ability")[0]["ability"] == "STR"
        assert static_items(body, "skill")[0]["skill_id"] == skill.id
        assert static_items(body, "saving_throw")[0]["ability"] == "DEX"
        assert static_items(body, "armor")[0]["armor_type"] == "LIGHT"
        weapon = static_items(body, "weapon")[0]
        assert weapon["weapon_category"] == "MARTIAL"
        assert weapon["item_id"] is None
        assert static_items(body, "spell")[0]["spell_id"] == spell.id

    async def test_weapon_effect_with_item_id(self, client, gm_token, create_feature, create_item):
        feature = await create_feature(name="Elf Weapon Training")
        item = await create_item(name="Longsword", item_type="WEAPON")

        response = await set_effects(client, gm_token, feature.id, {"weapon_effects": [{"item_id": item.id}]})

        assert response.status_code == 200
        weapon = static_items(response.json(), "weapon")[0]
        assert weapon["item_id"] == item.id
        assert weapon["weapon_category"] is None

    async def test_weapon_effect_neither_set_returns_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Bad Weapon")

        response = await set_effects(client, gm_token, feature.id, {"weapon_effects": [{}]})

        assert response.status_code == 422

    async def test_weapon_effect_both_set_returns_422(self, client, gm_token, create_feature, create_item):
        feature = await create_feature(name="Bad Weapon Both")
        item = await create_item(name="Longsword", item_type="WEAPON")

        response = await set_effects(
            client,
            gm_token,
            feature.id,
            {"weapon_effects": [{"weapon_category": "MARTIAL", "item_id": item.id}]},
        )

        assert response.status_code == 422

    async def test_spell_effect_with_spell_id(self, client, gm_token, create_feature, create_spell):
        feature = await create_feature(name="Spell Grantor")
        spell = await create_spell(name="Fireball", school="EVOCATION", level="LEVEL_3")

        response = await set_effects(client, gm_token, feature.id, {"spell_effects": [{"spell_id": spell.id}]})

        assert response.status_code == 200
        assert static_items(response.json(), "spell")[0]["spell_id"] == spell.id

    async def test_fixed_spell_effect_without_spell_id_is_rejected(self, client, gm_token, create_feature):
        feature = await create_feature(name="Any Spell Grant")

        response = await set_effects(client, gm_token, feature.id, {"spell_effects": [{}]})

        assert response.status_code == 422
        assert (await client.get(f"/features/{feature.id}/effects")).json()["static_groups"] == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestChoiceGroups:
    async def test_put_choice_groups_full_tree(self, client, gm_token, create_feature):
        feature = await create_feature(name="Resilient")

        response = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "ABILITY_SCORE",
                        "options": [
                            {"ability_effects": [{"ability": "STR", "amount": 1}]},
                            {"ability_effects": [{"ability": "DEX", "amount": 1}]},
                        ],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        groups = response.json()
        assert len(groups) == 1
        assert groups[0]["pick_count"] == 1
        assert "label" not in groups[0]
        assert len(groups[0]["options"]) == 2
        str_opt = next(o for o in groups[0]["options"] if o["ability_effects"][0]["ability"] == "STR")
        assert len(str_opt["ability_effects"]) == 1
        assert str_opt["ability_effects"][0]["ability"] == "STR"

    async def test_second_ability_choice_group_rejected(self, client, gm_token, create_feature):
        """A feature may offer only one choice group of type ABILITY_SCORE, not two."""
        feature = await create_feature(name="Double ASI")

        response = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "ABILITY_SCORE",
                        "options": [{"ability_effects": [{"ability": "STR", "amount": 1}]}],
                    },
                    {
                        "pick_count": 1,
                        "choice_type": "ABILITY_SCORE",
                        "options": [{"ability_effects": [{"ability": "DEX", "amount": 1}]}],
                    },
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_clear_choice_groups(self, client, gm_token, create_feature):
        feature = await create_feature(name="Temporary Choice")
        await client.put(
            f"/features/{feature.id}/choice-groups",
            json={"choice_groups": [{"pick_count": 1, "choice_type": "SKILL", "options": []}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        response = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={"choice_groups": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        assert response.json() == []

    async def test_updating_by_id_keeps_the_same_group_and_option_ids(self, client, gm_token, create_feature):
        feature = await create_feature(name="Stable Ids")
        first = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "ABILITY_SCORE",
                        "options": [{"ability_effects": [{"ability": "STR", "amount": 1}]}],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        group = first.json()[0]
        option = group["options"][0]

        response = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "id": group["id"],
                        "pick_count": 1,
                        "choice_type": "ABILITY_SCORE",
                        "options": [{"id": option["id"], "ability_effects": [{"ability": "STR", "amount": 2}]}],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        updated = response.json()[0]
        assert updated["id"] == group["id"]
        assert updated["options"][0]["id"] == option["id"]
        assert updated["options"][0]["ability_effects"][0]["amount"] == 2

    async def test_foreign_group_id_returns_422(self, client, gm_token, create_feature):
        feature_a = await create_feature(name="Group Owner A")
        feature_b = await create_feature(name="Group Owner B")
        created = await client.put(
            f"/features/{feature_a.id}/choice-groups",
            json={"choice_groups": [{"pick_count": 1, "choice_type": "SKILL", "options": []}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        stray_group_id = created.json()[0]["id"]

        response = await client.put(
            f"/features/{feature_b.id}/choice-groups",
            json={"choice_groups": [{"id": stray_group_id, "pick_count": 1, "choice_type": "SKILL", "options": []}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_get_choice_groups_open(self, client, create_feature):
        feature = await create_feature(name="Open Choice")

        response = await client.get(f"/features/{feature.id}/choice-groups")

        assert response.status_code == 200
        assert response.json() == []

    async def test_player_cannot_write_choice_groups(self, client, player_token, create_feature):
        feature = await create_feature(name="Player Choice Proof")

        response = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={"choice_groups": []},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestFeatureResponsesEmbedEffectTree:
    async def test_feature_detail_response_embeds_ability_effects(self, client, gm_token, create_feature):
        feature = await create_feature(name="Primal Champion")
        await set_effects(
            client,
            gm_token,
            feature.id,
            {"ability_effects": [{"ability": "STR", "amount": 4, "new_cap": 30}]},
        )

        response = await client.get(f"/features/{feature.id}")

        assert response.status_code == 200
        body = response.json()
        abilities = static_items(body, "ability")
        assert [{k: v for k, v in item.items() if k != "id"} for item in abilities] == [
            {"ability": "STR", "amount": 4, "new_cap": 30}
        ]
        assert body["has_static_effects"] is True

    async def test_feature_detail_embeds_whole_effect_tree(
        self, client, gm_token, create_feature, create_skill, create_item, create_spell
    ):
        feature = await create_feature(name="Primal Champion")
        skill = await create_skill(name="Stealth", ability="DEX")
        item = await create_item(name="Longsword", item_type="WEAPON")
        spell = await create_spell(name="Fireball", school="EVOCATION", level="LEVEL_3")

        await set_effects(
            client,
            gm_token,
            feature.id,
            {
                "ability_effects": [{"ability": "STR", "amount": 4, "new_cap": 30}],
                "skill_effects": [{"skill_id": skill.id}],
                "saving_throw_effects": [{"ability": "DEX"}],
                "armor_effects": [{"armor_type": "LIGHT"}],
                "weapon_effects": [{"weapon_category": "MARTIAL"}],
                "spell_effects": [{"spell_id": spell.id}],
            },
        )
        await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "ABILITY_SCORE",
                        "options": [{"ability_effects": [{"ability": "STR", "amount": 1}]}],
                    },
                    {
                        "pick_count": 1,
                        "choice_type": "SAVING_THROW",
                        "options": [{"saving_throw_effects": [{"ability": "STR"}]}],
                    },
                    {
                        "pick_count": 1,
                        "choice_type": "SKILL",
                        "options": [{"skill_effects": [{"skill_id": skill.id}]}],
                    },
                    {
                        "pick_count": 1,
                        "choice_type": "ARMOR",
                        "options": [{"armor_effects": [{"armor_type": "SHIELD"}]}],
                    },
                    {
                        "pick_count": 1,
                        "choice_type": "WEAPON",
                        "options": [{"weapon_effects": [{"item_id": item.id}]}],
                    },
                    {
                        "pick_count": 1,
                        "choice_type": "SPELL",
                        "options": [{"spell_effects": [{"spell_id": spell.id}]}],
                    },
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        response = await client.get(f"/features/{feature.id}")

        assert response.status_code == 200
        body = response.json()
        assert static_items(body, "ability")[0]["ability"] == "STR"
        assert static_items(body, "skill")[0]["skill_id"] == skill.id
        assert static_items(body, "saving_throw")[0]["ability"] == "DEX"
        assert static_items(body, "armor")[0]["armor_type"] == "LIGHT"
        assert static_items(body, "weapon")[0]["weapon_category"] == "MARTIAL"
        assert static_items(body, "spell")[0]["spell_id"] == spell.id
        assert len(body["choice_groups"]) == 6
        groups_by_type = {group["choice_type"]: group for group in body["choice_groups"]}
        assert groups_by_type["ABILITY_SCORE"]["options"][0]["ability_effects"][0]["ability"] == "STR"
        assert groups_by_type["SAVING_THROW"]["options"][0]["saving_throw_effects"][0]["ability"] == "STR"
        assert groups_by_type["SKILL"]["options"][0]["skill_effects"][0]["skill_id"] == skill.id
        assert groups_by_type["ARMOR"]["options"][0]["armor_effects"][0]["armor_type"] == "SHIELD"
        assert groups_by_type["WEAPON"]["options"][0]["weapon_effects"][0]["item_id"] == item.id
        assert groups_by_type["SPELL"]["options"][0]["spell_effects"][0]["spell_id"] == spell.id
        assert body["has_choices"] is True

    async def test_feature_detail_patch_returns_whole_effect_tree(self, client, gm_token, create_feature):
        feature = await create_feature(name="Dark Gaze")

        response = await client.patch(
            f"/features/{feature.id}",
            json={"description": "updated"},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["description"] == "updated"
        assert body["choice_groups"] == []
        assert body["static_groups"] == []

    async def test_race_feature_list_embeds_ability_effects(self, client, gm_token, create_race, create_feature):
        race = await create_race(name="Half-Orc")
        feature = await create_feature(name="Savage Attacks", source_type="RACE", race_id=race.id)
        await set_effects(
            client,
            gm_token,
            feature.id,
            {"ability_effects": [{"ability": "STR", "amount": 2, "new_cap": 30}]},
        )

        response = await client.get(f"/races/{race.id}/features")

        assert response.status_code == 200
        body = response.json()
        assert body[0]["name"] == "Savage Attacks"
        assert body[0]["has_static_effects"] is True
        assert "Сила" in body[0]["effects_summary"]

    async def test_fresh_feature_embeds_empty_static_groups(self, client, create_feature):
        feature = await create_feature(name="Plain")

        response = await client.get(f"/features/{feature.id}")

        assert response.status_code == 200
        assert response.json()["static_groups"] == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestFeatureEffectsReMaterialization:
    async def test_changing_effects_updates_character_without_write(
        self, client, gm, gm_token, create_class, create_character, create_feature
    ):
        feature_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id, name="Refresher", strength=14)
        feature = await create_feature(name="Mighty", source_type="CLASS", level=None)

        # Set initial fixed effect: STR +2
        resp = await set_effects(client, gm_token, feature.id, {"ability_effects": [{"ability": "STR", "amount": 2}]})
        assert resp.status_code == 200

        # GM-grant the feature to the character
        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201

        # Check STR total reflects the +2
        stats = (
            await client.get(
                f"/characters/{character.id}/stats",
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).json()
        assert stats["strength"]["total"] == 16
        assert any(c["amount"] == 2 for c in stats["strength"]["contributions"])

        # Change the effect to STR +5 (no character-side write)
        await set_effects(client, gm_token, feature.id, {"ability_effects": [{"ability": "STR", "amount": 5}]})

        # STR total now reflects +5
        stats_after = (
            await client.get(
                f"/characters/{character.id}/stats",
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).json()
        assert stats_after["strength"]["total"] == 19
        assert any(c["amount"] == 5 for c in stats_after["strength"]["contributions"])

        # GET /characters/{id} serves cached ability_scores — must also show
        # the new total (no stale cache after the effect edit).
        detail = (
            await client.get(
                f"/characters/{character.id}",
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).json()
        assert detail["ability_scores"]["strength_total"] == 19

    async def test_clearing_effects_updates_character(
        self, client, gm, gm_token, create_class, create_character, create_feature
    ):
        feature_class = await create_class(name="Wizard")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id, name="Clearer", strength=14)
        feature = await create_feature(name="Temporary", source_type="CLASS", level=None)

        await set_effects(client, gm_token, feature.id, {"ability_effects": [{"ability": "STR", "amount": 3}]})
        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201

        stats_before = (
            await client.get(
                f"/characters/{character.id}/stats",
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).json()
        assert stats_before["strength"]["total"] == 17

        # Clear the effect
        await set_effects(client, gm_token, feature.id, {"ability_effects": []})

        stats_after = (
            await client.get(
                f"/characters/{character.id}/stats",
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).json()
        assert stats_after["strength"]["total"] == 14


@pytest.mark.integration
@pytest.mark.asyncio
class TestChoiceGroupEditRevertsAnsweredPickToPending:
    async def test_removing_a_picked_option_reverts_the_grant_to_pending(
        self, client, gm, gm_token, create_class, create_character, create_feature
    ):
        feature_class = await create_class(name="Barbarian")
        character = await create_character(owner_id=gm.id, class_id=feature_class.id, name="Reverter", strength=10)
        feature = await create_feature(name="Stone's Endurance", source_type="CLASS", level=None)

        groups_resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "choice_type": "ABILITY_SCORE",
                        "options": [
                            {"ability_effects": [{"ability": "STR", "amount": 1}]},
                            {"ability_effects": [{"ability": "DEX", "amount": 1}]},
                        ],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert groups_resp.status_code == 200
        group = groups_resp.json()[0]
        str_option = next(o for o in group["options"] if o["ability_effects"][0]["ability"] == "STR")
        dex_option = next(o for o in group["options"] if o["ability_effects"][0]["ability"] == "DEX")

        grant_resp = await client.post(
            f"/characters/{character.id}/gm-panel/features",
            json={"feature_id": feature.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_resp.status_code == 201
        grant_id = grant_resp.json()["id"]

        answer_resp = await client.patch(
            f"/characters/{character.id}/features/{grant_id}/choices",
            json={"answers": [{"choice_group_id": group["id"], "choice_option_id": str_option["id"]}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert answer_resp.status_code == 200
        assert answer_resp.json()["groups"] == []

        # Remove the STR option (keep only DEX) — the character's stored pick points at it.
        removed_resp = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "id": group["id"],
                        "pick_count": 1,
                        "choice_type": "ABILITY_SCORE",
                        "options": [{"id": dex_option["id"], "ability_effects": [{"ability": "DEX", "amount": 1}]}],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert removed_resp.status_code == 200

        pending = await client.get(
            f"/characters/{character.id}/grants/pending",
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert pending.status_code == 200
        pending_feature_ids = {entry["feature_id"] for entry in pending.json()}
        assert feature.id in pending_feature_ids


@pytest.mark.integration
@pytest.mark.asyncio
class TestFeatureEffectsAuthEdgeCases:
    async def test_get_unknown_feature_returns_404(self, client):
        response = await client.get("/features/999999/effects")
        assert response.status_code == 404

    async def test_put_unknown_feature_returns_404(self, client, gm_token):
        response = await set_effects(client, gm_token, 999999, {"ability_effects": []})
        assert response.status_code == 404

    async def test_get_choice_groups_unknown_feature_returns_404(self, client):
        response = await client.get("/features/999999/choice-groups")
        assert response.status_code == 404

    async def test_put_choice_groups_unknown_feature_returns_404(self, client, gm_token):
        response = await client.put(
            "/features/999999/choice-groups",
            json={"choice_groups": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 404

    async def test_unauthenticated_get_effects_open(self, client, create_feature):
        feature = await create_feature(name="NoAuth")
        response = await client.get(f"/features/{feature.id}/effects")
        assert response.status_code == 200

    async def test_unauthenticated_get_choice_groups_open(self, client, create_feature):
        feature = await create_feature(name="NoAuthChoice")
        response = await client.get(f"/features/{feature.id}/choice-groups")
        assert response.status_code == 200
