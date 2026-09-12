"""Tests for the feature effects endpoints: GET/PUT /features/{id}/effects and choice-groups."""

import pytest


async def set_effects(client, gm_token, feature_id, payload):
    return await client.put(
        f"/features/{feature_id}/effects",
        json=payload,
        headers={"Authorization": f"Bearer {gm_token}"},
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestFeatureEffectsCrud:
    async def test_empty_by_default(self, client, gm_token, create_feature):
        feature = await create_feature(name="Plain Feature")

        response = await client.get(f"/features/{feature.id}/effects")

        assert response.status_code == 200
        body = response.json()
        assert body["feature_id"] == feature.id
        assert body["ability_effects"] == []
        assert body["skill_effects"] == []
        assert body["saving_throw_effects"] == []
        assert body["armor_effects"] == []
        assert body["weapon_effects"] == []
        assert body["spell_effects"] == []
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
        assert {item["ability"]: item["amount"] for item in body["ability_effects"]} == {"STR": 4, "CON": 4}
        assert body["ability_effects"][0]["new_cap"] == 24

    async def test_set_is_a_full_replace(self, client, gm_token, create_feature):
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
        abilities = {item["ability"] for item in response.json()["ability_effects"]}
        assert abilities == {"CHA"}

    async def test_clear_with_empty_list(self, client, gm_token, create_feature):
        feature = await create_feature(name="Temporary Effect")
        await set_effects(client, gm_token, feature.id, {"ability_effects": [{"ability": "WIS", "amount": 1}]})

        response = await set_effects(client, gm_token, feature.id, {"ability_effects": []})

        assert response.status_code == 200
        assert response.json()["ability_effects"] == []

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
    async def test_put_all_six_effect_types(self, client, gm_token, create_feature, create_skill, create_item, create_spell):
        feature = await create_feature(name="Epic Feature", source_type="CLASS", level=None)
        skill = await create_skill(key="STEALTH", name="Stealth", ability="DEX")
        item = await create_item(name="Longsword", item_type="WEAPON")
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
        assert len(body["ability_effects"]) == 1
        assert body["ability_effects"][0]["ability"] == "STR"
        assert len(body["skill_effects"]) == 1
        assert body["skill_effects"][0]["skill_id"] == skill.id
        assert len(body["saving_throw_effects"]) == 1
        assert body["saving_throw_effects"][0]["ability"] == "DEX"
        assert len(body["armor_effects"]) == 1
        assert body["armor_effects"][0]["armor_type"] == "LIGHT"
        assert len(body["weapon_effects"]) == 1
        assert body["weapon_effects"][0]["weapon_category"] == "MARTIAL"
        assert body["weapon_effects"][0]["item_id"] is None
        assert len(body["spell_effects"]) == 1
        assert body["spell_effects"][0]["spell_id"] == spell.id

    async def test_weapon_effect_with_item_id(self, client, gm_token, create_feature, create_item):
        feature = await create_feature(name="Elf Weapon Training")
        item = await create_item(name="Longsword", item_type="WEAPON")

        response = await set_effects(
            client, gm_token, feature.id, {"weapon_effects": [{"item_id": item.id}]}
        )

        assert response.status_code == 200
        assert response.json()["weapon_effects"][0]["item_id"] == item.id
        assert response.json()["weapon_effects"][0]["weapon_category"] is None

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

        response = await set_effects(
            client, gm_token, feature.id, {"spell_effects": [{"spell_id": spell.id}]}
        )

        assert response.status_code == 200
        assert response.json()["spell_effects"][0]["spell_id"] == spell.id

    async def test_spell_effect_with_open_filter(self, client, gm_token, create_feature):
        feature = await create_feature(name="School Grant")

        response = await set_effects(
            client,
            gm_token,
            feature.id,
            {"spell_effects": [{"spell_school": "EVOCATION", "spell_level_max": "LEVEL_3"}]},
        )

        assert response.status_code == 200
        effect = response.json()["spell_effects"][0]
        assert effect["spell_id"] is None
        assert effect["spell_school"] == "EVOCATION"
        assert effect["spell_level_max"] == "LEVEL_3"

    async def test_spell_effect_mixed_returns_422(self, client, gm_token, create_feature, create_spell):
        feature = await create_feature(name="Bad Spell Mix")
        spell = await create_spell(name="Fireball", school="EVOCATION", level="LEVEL_3")

        response = await set_effects(
            client,
            gm_token,
            feature.id,
            {"spell_effects": [{"spell_id": spell.id, "spell_school": "EVOCATION"}]},
        )

        assert response.status_code == 422


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
                        "label": "Choose an ability",
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
        assert groups[0]["label"] == "Choose an ability"
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
                        "label": "Choose an ability",
                        "options": [{"ability_effects": [{"ability": "STR", "amount": 1}]}],
                    },
                    {
                        "pick_count": 1,
                        "choice_type": "ABILITY_SCORE",
                        "label": "Choose another ability",
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
class TestFeatureResponsesEmbedAbilityEffects:
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
        assert [{k: v for k, v in item.items() if k != "id"} for item in body["ability_effects"]] == [
            {"ability": "STR", "amount": 4, "new_cap": 30}
        ]

    async def test_feature_detail_embeds_whole_effect_tree(
        self, client, gm_token, create_feature, create_skill, create_item, create_spell
    ):
        feature = await create_feature(name="Primal Champion")
        skill = await create_skill(key="STEALTH", name="Stealth", ability="DEX")
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
                        "label": "Ability boon",
                        "options": [{"ability_effects": [{"ability": "STR", "amount": 1}]}],
                    },
                    {
                        "pick_count": 1,
                        "choice_type": "SAVING_THROW",
                        "label": "Save boon",
                        "options": [{"saving_throw_effects": [{"ability": "STR"}]}],
                    },
                    {
                        "pick_count": 1,
                        "choice_type": "SKILL",
                        "label": "Skill boon",
                        "options": [{"skill_effects": [{"skill_id": skill.id}]}],
                    },
                    {
                        "pick_count": 1,
                        "choice_type": "ARMOR",
                        "label": "Armor boon",
                        "options": [{"armor_effects": [{"armor_type": "SHIELD"}]}],
                    },
                    {
                        "pick_count": 1,
                        "choice_type": "WEAPON",
                        "label": "Weapon boon",
                        "options": [{"weapon_effects": [{"item_id": item.id}]}],
                    },
                    {
                        "pick_count": 1,
                        "choice_type": "SPELL",
                        "label": "Spell boon",
                        "options": [{"spell_effects": [{"spell_id": spell.id}]}],
                    },
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        response = await client.get(f"/features/{feature.id}")

        assert response.status_code == 200
        body = response.json()
        assert [{k: v for k, v in item.items() if k != "id"} for item in body["ability_effects"]] == [
            {"ability": "STR", "amount": 4, "new_cap": 30}
        ]
        assert body["skill_effects"][0]["skill_id"] == skill.id
        assert body["saving_throw_effects"][0]["ability"] == "DEX"
        assert body["armor_effects"][0]["armor_type"] == "LIGHT"
        assert body["weapon_effects"][0]["weapon_category"] == "MARTIAL"
        assert body["spell_effects"][0]["spell_id"] == spell.id
        assert len(body["choice_groups"]) == 6
        groups_by_type = {group["choice_type"]: group for group in body["choice_groups"]}
        assert groups_by_type["ABILITY_SCORE"]["options"][0]["ability_effects"][0]["ability"] == "STR"
        assert groups_by_type["SAVING_THROW"]["options"][0]["saving_throw_effects"][0]["ability"] == "STR"
        assert groups_by_type["SKILL"]["options"][0]["skill_effects"][0]["skill_id"] == skill.id
        assert groups_by_type["ARMOR"]["options"][0]["armor_effects"][0]["armor_type"] == "SHIELD"
        assert groups_by_type["WEAPON"]["options"][0]["weapon_effects"][0]["item_id"] == item.id
        assert groups_by_type["SPELL"]["options"][0]["spell_effects"][0]["spell_id"] == spell.id

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
        assert body["skill_effects"] == []
        assert body["saving_throw_effects"] == []

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
        assert [{k: v for k, v in item.items() if k != "id"} for item in body[0]["ability_effects"]] == [
            {"ability": "STR", "amount": 2, "new_cap": 30}
        ]

    async def test_fresh_feature_embeds_empty_ability_effects(self, client, create_feature):
        feature = await create_feature(name="Plain")

        response = await client.get(f"/features/{feature.id}")

        assert response.status_code == 200
        assert response.json()["ability_effects"] == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestFeatureEffectsReMaterialization:
    async def test_changing_effects_updates_character_without_write(
        self, client, gm, gm_token, create_class, create_character, create_feature
    ):
        feature_class = await create_class(name="Fighter")
        character = await create_character(
            owner_id=gm.id, class_id=feature_class.id, name="Refresher", strength=14
        )
        feature = await create_feature(name="Mighty", source_type="CLASS", level=None)

        # Set initial fixed effect: STR +2
        resp = await set_effects(
            client, gm_token, feature.id, {"ability_effects": [{"ability": "STR", "amount": 2}]}
        )
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
        await set_effects(
            client, gm_token, feature.id, {"ability_effects": [{"ability": "STR", "amount": 5}]}
        )

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
        character = await create_character(
            owner_id=gm.id, class_id=feature_class.id, name="Clearer", strength=14
        )
        feature = await create_feature(name="Temporary", source_type="CLASS", level=None)

        await set_effects(
            client, gm_token, feature.id, {"ability_effects": [{"ability": "STR", "amount": 3}]}
        )
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
