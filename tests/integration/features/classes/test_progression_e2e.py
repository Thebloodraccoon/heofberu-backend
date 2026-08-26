"""
End-to-end tests for the class spell-slot progression endpoint:
PUT /classes/spell-slots full-replaces a single class level's rows,
accepts CANTRIP rows, and rejects bad class levels, duplicate spell
levels, and missing classes.
"""

import pytest


async def set_slots(client, gm_token, class_id, class_level, slots):
    return await client.put(
        "/classes/spell-slots",
        params={"class_id": class_id, "class_level": class_level},
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

        response = await client.get("/classes/progression", params={"class_id": character_class.id})
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
    async def test_put_below_class_level_one_returns_400(self, client, gm_token, create_class):
        character_class = await create_class(name="Wizard", spellcasting_ability="INT")

        response = await set_slots(client, gm_token, character_class.id, 0, [{"spell_level": "LEVEL_1", "slots": 1}])

        assert response.status_code == 400

    async def test_put_above_class_level_twenty_returns_400(self, client, gm_token, create_class):
        character_class = await create_class(name="Wizard", spellcasting_ability="INT")

        response = await set_slots(client, gm_token, character_class.id, 21, [])

        assert response.status_code == 400

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

    async def test_put_unknown_class_returns_404(self, client, gm_token):
        response = await set_slots(client, gm_token, 999999, 1, [{"spell_level": "LEVEL_1", "slots": 2}])

        assert response.status_code == 404

    async def test_player_cannot_set_spell_slots(self, client, player_token, gm_token, create_class):
        character_class = await create_class(name="Wizard", spellcasting_ability="INT")

        response = await client.put(
            "/classes/spell-slots",
            params={"class_id": character_class.id, "class_level": 1},
            json={"slots": [{"spell_level": "LEVEL_1", "slots": 9}]},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
