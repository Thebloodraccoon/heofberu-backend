"""
End-to-end tests for the class spell-slot progression endpoint:
PUT /classes/spell-slots full-replaces a single class level's rows,
accepts CANTRIP rows, and rejects bad class levels (422), negative slots, duplicate spell
levels, and missing classes; GET /progression builds the 1-20 table, including
class and subclass features.
"""

import pytest


async def set_slots(client, gm_token, class_id, class_level, slots):
    return await client.put(
        f"/classes/{class_id}/spell-slots",
        params={"class_level": class_level},
        json={"slots": slots},
        headers={"Authorization": f"Bearer {gm_token}"},
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestSpellSlotReplacement:
    async def test_put_replaces_only_the_target_class_level(self, client, gm_token, create_class):
        character_class = await create_class(name="Wizard", spellcasting_ability="INT")

        first = await set_slots(
            client,
            gm_token,
            character_class.id,
            1,
            [{"spell_level": "CANTRIP", "slots": 3}, {"spell_level": "LEVEL_1", "slots": 2}],
        )
        assert first.status_code == 200

        other_level = await set_slots(client, gm_token, character_class.id, 5, [{"spell_level": "LEVEL_3", "slots": 2}])
        assert other_level.status_code == 200

        replacement = await set_slots(client, gm_token, character_class.id, 1, [{"spell_level": "LEVEL_1", "slots": 4}])
        assert replacement.status_code == 200

        fetched_response = await client.get(f"/classes/{character_class.id}")
        assert fetched_response.status_code == 200
        assert fetched_response.json()["spell_slot_progression"] == [
            {"class_level": 1, "spell_level": "LEVEL_1", "slots": 4},
            {"class_level": 5, "spell_level": "LEVEL_3", "slots": 2},
        ]

    async def test_put_accepts_a_cantrip_row(self, client, gm_token, create_class):
        character_class = await create_class(name="Warlock", spellcasting_ability="CHA")

        response = await set_slots(client, gm_token, character_class.id, 1, [{"spell_level": "CANTRIP", "slots": 2}])

        assert response.status_code == 200
        assert response.json()["spell_slot_progression"] == [{"class_level": 1, "spell_level": "CANTRIP", "slots": 2}]

    async def test_put_with_empty_list_clears_the_level(self, client, gm_token, create_class):
        character_class = await create_class(name="Cleric", spellcasting_ability="WIS")

        seeded = await set_slots(client, gm_token, character_class.id, 1, [{"spell_level": "LEVEL_1", "slots": 2}])
        assert seeded.status_code == 200

        cleared = await set_slots(client, gm_token, character_class.id, 1, [])
        assert cleared.status_code == 200
        assert cleared.json()["spell_slot_progression"] == []

    async def test_progression_table_reflects_seeded_rows(self, client, gm_token, create_class):
        character_class = await create_class(name="Bard", spellcasting_ability="CHA")

        seeded = await set_slots(
            client,
            gm_token,
            character_class.id,
            1,
            [{"spell_level": "CANTRIP", "slots": 2}, {"spell_level": "LEVEL_1", "slots": 2}],
        )
        assert seeded.status_code == 200

        response = await client.get(f"/classes/{character_class.id}/progression")
        assert response.status_code == 200
        body = response.json()
        assert body["class_id"] == character_class.id
        assert body["class_name"] == "Bard"
        assert len(body["rows"]) == 20
        assert body["rows"][0]["level"] == 1
        assert body["rows"][0]["proficiency_bonus"] == 2
        assert body["rows"][0]["spell_slots"] == {"CANTRIP": 2, "LEVEL_1": 2}
        assert body["rows"][4]["spell_slots"] == {}
        assert body["rows"][4]["proficiency_bonus"] == 3


@pytest.mark.integration
@pytest.mark.asyncio
class TestSpellSlotValidation:
    async def test_put_below_class_level_one_returns_422(self, client, gm_token, create_class):
        character_class = await create_class(name="Wizard", spellcasting_ability="INT")

        response = await set_slots(client, gm_token, character_class.id, 0, [{"spell_level": "LEVEL_1", "slots": 1}])

        assert response.status_code == 422

    async def test_put_above_class_level_twenty_returns_422(self, client, gm_token, create_class):
        character_class = await create_class(name="Wizard", spellcasting_ability="INT")

        response = await set_slots(client, gm_token, character_class.id, 21, [])

        assert response.status_code == 422

    async def test_put_duplicate_spell_levels_returns_422(self, client, gm_token, create_class):
        character_class = await create_class(name="Wizard", spellcasting_ability="INT")

        response = await set_slots(
            client,
            gm_token,
            character_class.id,
            1,
            [{"spell_level": "LEVEL_1", "slots": 2}, {"spell_level": "LEVEL_1", "slots": 3}],
        )

        assert response.status_code == 422

    async def test_put_unknown_spell_level_returns_422(self, client, gm_token, create_class):
        character_class = await create_class(name="Wizard", spellcasting_ability="INT")

        response = await set_slots(client, gm_token, character_class.id, 1, [{"spell_level": "LEVEL_11", "slots": 2}])

        assert response.status_code == 422

    async def test_put_negative_slots_returns_422(self, client, gm_token, create_class):
        character_class = await create_class(name="Wizard", spellcasting_ability="INT")

        response = await set_slots(client, gm_token, character_class.id, 1, [{"spell_level": "LEVEL_1", "slots": -1}])

        assert response.status_code == 422

    async def test_put_unknown_class_returns_404(self, client, gm_token):
        response = await set_slots(client, gm_token, 999999, 1, [{"spell_level": "LEVEL_1", "slots": 2}])

        assert response.status_code == 404

    async def test_player_cannot_set_spell_slots(self, client, player_token, gm_token, create_class):
        character_class = await create_class(name="Wizard", spellcasting_ability="INT")

        response = await client.put(
            f"/classes/{character_class.id}/spell-slots",
            params={"class_level": 1},
            json={"slots": [{"spell_level": "LEVEL_1", "slots": 9}]},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestProgressionWithFeatures:
    async def test_class_and_subclass_features_land_on_their_levels(
        self, client, gm_token, create_class, create_subclass, create_feature, create_skill
    ):
        character_class = await create_class(name="Fighter")
        champion = await create_subclass(class_id=character_class.id, name="Champion")
        master = await create_subclass(class_id=character_class.id, name="Battle Master")
        skill = await create_skill(name="Athletics", ability="STR")
        second_wind = await create_feature(
            name="Second Wind", source_type="CLASS", class_id=character_class.id, level=1
        )
        await create_feature(name="Extra Attack", source_type="CLASS", class_id=character_class.id, level=5)
        await create_feature(name="Improved Critical", source_type="SUBCLASS", subclass_id=champion.id, level=3)
        await create_feature(name="Combat Superiority", source_type="SUBCLASS", subclass_id=master.id, level=3)
        effects = await client.put(
            f"/features/{second_wind.id}/effects",
            json={"static_groups": [{"effect_type": "skill", "items": [{"skill_id": skill.id}]}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert effects.status_code == 200

        response = await client.get(f"/classes/{character_class.id}/progression")

        assert response.status_code == 200, response.text
        rows = response.json()["rows"]
        assert [f["name"] for f in rows[0]["class_features"]] == ["Second Wind"]
        assert rows[0]["class_features"][0]["has_static_effects"] is True
        assert "Athletics" in rows[0]["class_features"][0]["effects_summary"]
        assert rows[0]["subclass_features"] == []
        assert [f["name"] for f in rows[4]["class_features"]] == ["Extra Attack"]
        level_three = rows[2]
        assert level_three["class_features"] == []
        assert {(f["name"], f["subclass_id"]) for f in level_three["subclass_features"]} == {
            ("Improved Critical", champion.id),
            ("Combat Superiority", master.id),
        }

    async def test_features_of_another_class_are_not_included(self, client, create_class, create_feature):
        fighter = await create_class(name="Fighter")
        rogue = await create_class(name="Rogue")
        await create_feature(name="Sneak Attack", source_type="CLASS", class_id=rogue.id, level=1)

        rows = (await client.get(f"/classes/{fighter.id}/progression")).json()["rows"]

        assert all(row["class_features"] == [] and row["subclass_features"] == [] for row in rows)

    async def test_progression_is_cached_and_refreshed_by_feature_and_slot_writes(
        self, caching_on, client, gm_token, create_class
    ):
        character_class = await create_class(name="Wizard", spellcasting_ability="INT")
        class_id = character_class.id
        path = f"/classes/{class_id}/progression"
        headers = {"Authorization": f"Bearer {gm_token}"}
        assert (await client.get(path)).json()["rows"][0]["class_features"] == []

        added = await client.post(
            "/features",
            json={"name": "Arcane Recovery", "level": 1, "source_type": "CLASS", "class_id": class_id},
            headers=headers,
        )
        assert added.status_code == 201
        rows = (await client.get(path)).json()["rows"]
        assert [f["name"] for f in rows[0]["class_features"]] == ["Arcane Recovery"]

        await set_slots(client, gm_token, class_id, 2, [{"spell_level": "LEVEL_1", "slots": 3}])
        assert (await client.get(path)).json()["rows"][1]["spell_slots"] == {"LEVEL_1": 3}

        removed = await client.delete(f"/features/{added.json()['id']}", headers=headers)
        assert removed.status_code == 204
        assert (await client.get(path)).json()["rows"][0]["class_features"] == []

    async def test_unknown_class_returns_404(self, client):
        assert (await client.get("/classes/999999/progression")).status_code == 404
