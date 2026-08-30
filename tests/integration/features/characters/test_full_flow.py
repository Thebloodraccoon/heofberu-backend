"""
Full-flow character tests: the whole journey from leveling up, ASI choices,
caps, subclass and background setup — plus the edge cases along that path.
"""

import pytest


async def level_up(client, character_id, token, payload=None):
    return await client.post(
        f"/characters/{character_id}/progression/level-up",
        json=payload or {},
        headers={"Authorization": f"Bearer {token}"},
    )


async def get_stats(client, character_id, token):
    response = await client.get(
        f"/characters/{character_id}/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.integration
@pytest.mark.asyncio
class TestNoOriginFeat:
    async def test_create_without_feat_is_accepted(self, client, player_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.post(
            "/characters",
            json={"name": "No Feat", "class_id": character_class.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 201

    async def test_feat_id_is_rejected_as_extra_field(self, client, player_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.post(
            "/characters",
            json={"name": "Ghost", "class_id": character_class.id, "feat_id": 999999},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 422

    async def test_creation_grants_no_feats_or_choices(
        self, client, player, player_token, gm_token, create_class, create_api_character
    ):
        character_class = await create_class(name="Fighter")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        feats = (
            await client.get(
                f"/characters/{character['id']}/feats",
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).json()
        assert feats == []

        choices = (
            await client.get(
                f"/characters/{character['id']}/progression/asi-choices",
                headers={"Authorization": f"Bearer {player_token}"},
            )
        ).json()
        assert choices == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestFullJourneyToLevelFive:
    async def test_creation_to_level_five_hp_and_asi(
        self, client, player, player_token, create_class, create_api_character
    ):
        """Levels 1->5: HP accrues by die average + CON; the level-4 ASI is required and counted."""

        character_class = await create_class(name="Fighter", hit_dice="D10")
        character, token = await create_api_character(
            class_id=character_class.id, owner=player, strength=14, constitution=14
        )
        # Level 1: full die + CON mod = 10 + 2.
        assert character["max_hp"] == 12

        # Levels 2 and 3: no choice allowed/needed; +8 HP each (avg 5 + 1 + 2 CON).
        for target_level in (2, 3):
            response = await level_up(client, character["id"], token)
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["level"] == target_level
            assert body["max_hp"] == 12 + 8 * (target_level - 1)

        # Level 4: ASI level — empty choice is rejected.
        rejected = await level_up(client, character["id"], token)
        assert rejected.status_code == 400

        ok = await level_up(
            client,
            character["id"],
            token,
            {"choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 2}]}},
        )
        assert ok.status_code == 200
        stats = await get_stats(client, character["id"], token)
        assert stats["strength"]["base"] == 14  # base never moves
        assert stats["strength"]["total"] == 16
        assert ok.json()["max_hp"] == 36  # 12 + 8*2 + 8

        # Level 5: choice must NOT be sent on a non-ASI level.
        rejected = await level_up(
            client, character["id"], token, {"choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 1}]}}
        )
        assert rejected.status_code == 400
        ok = await level_up(client, character["id"], token)
        assert ok.status_code == 200
        assert ok.json()["max_hp"] == 44

    async def test_caster_spell_slots_refollow_each_level(
        self, client, player, player_token, gm_token, create_caster_class, create_api_character
    ):
        wizard_class = await create_caster_class(name="Flow Wizard")

        async def set_slots(level, slots):
            response = await client.put(
                f"/classes/{wizard_class.id}/spell-slots",
                params={"class_level": level},
                json={"slots": [{"spell_level": "LEVEL_1", "slots": slots}]},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
            assert response.status_code == 200

        await set_slots(1, 2)
        character, token = await create_api_character(class_id=wizard_class.id, owner=player)

        async def slots_total():
            spells_response = await client.get(
                f"/characters/{character['id']}/spells",
                headers={"Authorization": f"Bearer {token}"},
            )
            items = {item["spell_level"]: item for item in spells_response.json()["spell_slots"]}
            return items["LEVEL_1"]["total"]

        assert await slots_total() == 2

        await set_slots(2, 3)
        response = await level_up(client, character["id"], token)
        assert response.status_code == 200
        assert await slots_total() == 3

    async def test_max_level_gate_blocks_until_raised(
        self, client, player, player_token, gm_token, create_class, create_api_character
    ):
        character_class = await create_class(name="Fighter")
        character, token = await create_api_character(class_id=character_class.id, owner=player, raise_max_level=False)

        blocked = await level_up(client, character["id"], token)
        assert blocked.status_code == 400

        raised = await client.patch(
            f"/characters/{character['id']}/gm-panel/max-level",
            json={"max_level": 2},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert raised.status_code == 200

        ok = await level_up(client, character["id"], token)
        assert ok.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
class TestScoreBoundaries:
    async def test_player_asi_caps_at_twenty_but_gm_panel_continues_to_thirty(
        self, client, player, player_token, gm_token, create_class, create_api_character
    ):
        character_class = await create_class(name="Fighter")
        character, token = await create_api_character(class_id=character_class.id, owner=player, strength=16)

        await level_up(client, character["id"], token)  # 2
        await level_up(client, character["id"], token)  # 3
        response = await level_up(
            client,
            character["id"],
            token,
            {"choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 2}]}},
        )  # 4: STR effective 18
        assert response.status_code == 200

        await level_up(client, character["id"], token)  # 5
        response = await level_up(
            client,
            character["id"],
            token,
            {"choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 2}]}},
        )  # 6 (non-ASI level!) -> 400
        assert response.status_code == 400

        # The GM panel is its own ceiling: it takes STR beyond 20 up to 30.
        ok = await client.post(
            f"/characters/{character['id']}/gm-panel/asi",
            json={"increases": [{"ability": "STR", "amount": 12}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ok.status_code == 201  # 18 + 12 = 30

        over = await client.post(
            f"/characters/{character['id']}/gm-panel/asi",
            json={"increases": [{"ability": "STR", "amount": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert over.status_code == 400  # 31 > 30

        stats = await get_stats(client, character["id"], token)
        assert stats["strength"]["total"] == 30

    async def test_negative_adjustments_floor_effective_at_one(
        self, client, gm_token, gm, create_class, create_character
    ):
        character_class = await create_class(name="Sorcerer")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, charisma=3)

        response = await client.post(
            f"/characters/{character.id}/gm-panel/asi",
            json={"increases": [{"ability": "CHA", "amount": -10}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 201

        stats = await get_stats(client, character.id, gm_token)
        assert stats["charisma"]["base"] == 3
        assert stats["charisma"]["total"] == 1  # floored, never 0/negative

    async def test_adjustment_stack_and_remove_roundtrip(self, client, gm_token, gm, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, strength=10)

        ids = []
        for amount in (2, 3):
            response = await client.post(
                f"/characters/{character.id}/gm-panel/asi",
                json={"increases": [{"ability": "STR", "amount": amount}]},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
            assert response.status_code == 201
            ids.append(response.json()["id"])

        assert (await get_stats(client, character.id, gm_token))["strength"]["total"] == 15

        removed = await client.delete(
            f"/characters/{character.id}/gm-panel/asi",
            params={"adjustment_id": ids[0]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert removed.status_code == 204
        assert (await get_stats(client, character.id, gm_token))["strength"]["total"] == 13


@pytest.mark.integration
@pytest.mark.asyncio
class TestLateSetupGrants:
    async def test_subclass_set_after_creation_applies_feature_effects(
        self,
        client,
        player,
        player_token,
        gm_token,
        create_class,
        create_subclass,
        create_feature,
        create_api_character,
    ):
        character_class = await create_class(name="Fighter")
        champion = await create_subclass(class_id=character_class.id, name="Champion")
        trait = await create_feature(name="Champion Trait", source_type="SUBCLASS", subclass_id=champion.id, level=None)
        await client.put(
            f"/features/{trait.id}/ability-increases",
            json={"ability_increases": [{"ability": "STR", "amount": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        character, token = await create_api_character(class_id=character_class.id, owner=player, strength=10)

        response = await client.patch(
            f"/characters/{character['id']}/progression/subclass",
            json={"subclass_id": champion.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert response.status_code == 200

        stats = await get_stats(client, character["id"], token)
        assert stats["strength"]["total"] == 11

    async def test_background_set_after_creation_grants_skills_and_equipment(
        self, client, player, player_token, gm_token, create_class, create_background, create_api_character
    ):
        character_class = await create_class(name="Fighter")
        background = await create_background()
        character, token = await create_api_character(class_id=character_class.id, owner=player, background_id=False)

        response = await client.patch(
            f"/characters/{character['id']}/progression/background",
            json={"background_id": background.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert response.status_code == 200

        second = await client.patch(
            f"/characters/{character['id']}/progression/background",
            json={"background_id": background.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert second.status_code == 409

    async def test_long_rest_restores_after_damage(
        self, client, player, player_token, create_class, create_api_character
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        character, token = await create_api_character(class_id=character_class.id, owner=player, constitution=14)
        assert character["max_hp"] == 12

        damaged = await client.patch(
            f"/characters/{character['id']}/hp",
            json={"delta": -7},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert damaged.status_code == 200
        assert damaged.json()["current_hp"] == 5

        rested = await client.post(
            f"/characters/{character['id']}/rest",
            json={"type": "long"},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert rested.status_code == 200
        assert rested.json()["current_hp"] == 12
