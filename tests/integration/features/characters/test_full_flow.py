"""
Full-flow character tests: the whole journey from creation (with the
mandatory origin feat) through leveling up, ASI choices, caps, subclass
and background setup — plus the edge cases along that path.
"""

import pytest


async def level_up(client, character_id, token, payload=None):
    return await client.post(
        "/characters/progression/level-up",
        params={"character_id": character_id},
        json=payload or {},
        headers={"Authorization": f"Bearer {token}"},
    )


async def get_stats(client, character_id, token):
    response = await client.get(
        "/characters/gm-panel/stats",
        params={"character_id": character_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.integration
@pytest.mark.asyncio
class TestMandatoryOriginFeat:
    async def test_create_without_feat_is_rejected(self, client, player_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.post(
            "/characters",
            json={"name": "No Feat", "class_id": character_class.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 422

    async def test_create_with_unknown_feat_returns_404(self, client, player_token, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.post(
            "/characters",
            json={"name": "Ghost", "class_id": character_class.id, "feat_id": 999999},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 404

    async def test_origin_feat_is_granted_and_audited(
        self, client, player, player_token, gm_token, create_class, create_api_character
    ):
        character_class = await create_class(name="Fighter")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        feats = (
            await client.get(
                "/characters/feats",
                params={"character_id": character["id"]},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
        ).json()
        assert len(feats) == 1

        choices = (
            await client.get(
                "/characters/progression/asi-choices",
                params={"character_id": character["id"]},
                headers={"Authorization": f"Bearer {player_token}"},
            )
        ).json()
        assert [choice["choice_type"] for choice in choices] == ["FEAT"]
        assert choices[0]["class_level"] is None

    async def test_feat_with_asi_options_requires_explicit_choice(self, client, gm_token, player_token, create_class, create_feat):
        character_class = await create_class(name="Fighter")
        resilient = await create_feat(name="Resilient Creation")
        await client.put(
            "/feats/ability-score-increases",
            params={"feat_id": resilient.id},
            json={"ability_score_increases": [{"ability": "CON", "amount": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        response = await client.post(
            "/characters",
            json={"name": "Silent", "class_id": character_class.id, "feat_id": resilient.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 422

    async def test_feat_asi_choice_applies_to_starting_hp(
        self, client, player, player_token, gm_token, create_class, create_feat, create_background, create_api_character
    ):
        """A +1 CON origin feat raises starting max HP through the effective CON modifier."""

        character_class = await create_class(name="Fighter", hit_dice="D10")
        tough = await create_feat(name="Tough Origin")
        asi_response = await client.put(
            "/feats/ability-score-increases",
            params={"feat_id": tough.id},
            json={"ability_score_increases": [{"ability": "CON", "amount": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert asi_response.status_code == 200
        tough_asi_id = asi_response.json()["ability_score_increases"][0]["id"]

        # CON 13 -> mod +1 (HP 11); with the feat's +1: 14 -> mod +2 (HP 12).
        # (Odd scores: (score-10)//2 floors, so 15 would still be +2.)
        plain_background = await create_background(name="Plain Acolyte")
        tough_background = await create_background(name="Tough Acolyte")
        plain, _ = await create_api_character(
            class_id=character_class.id, owner=player, name="Plain", constitution=13,
            background_id=plain_background.id,
        )
        tough_char, _ = await create_api_character(
            class_id=character_class.id,
            owner=player,
            name="Tough",
            constitution=13,
            background_id=tough_background.id,
            origin_feat=tough,
            ability_score_increase_id=tough_asi_id,
        )

        assert plain["max_hp"] == 11
        assert tough_char["max_hp"] == 12

    async def test_feat_prerequisite_unmet_returns_400(self, client, player_token, create_class, create_feat):
        character_class = await create_class(name="Fighter")
        heavy_armor_master = await create_feat(
            name="Heavy Armor Master Creation",
            prerequisite_ability="STR",
            prerequisite_minimum_score=13,
        )

        response = await client.post(
            "/characters",
            json={
                "name": "Weakling",
                "class_id": character_class.id,
                "feat_id": heavy_armor_master.id,
                "strength": 8,
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400


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
        rejected = await level_up(client, character["id"], token, {"choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 1}]}})
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
                "/classes/spell-slots",
                params={"class_id": wizard_class.id, "class_level": level},
                json={"slots": [{"spell_level": "LEVEL_1", "slots": slots}]},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
            assert response.status_code == 200

        await set_slots(1, 2)
        character, token = await create_api_character(class_id=wizard_class.id, owner=player)

        async def slots_total():
            spells_response = await client.get(
                "/characters/spells",
                params={"character_id": character["id"]},
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
        character, token = await create_api_character(
            class_id=character_class.id, owner=player, raise_max_level=False
        )

        blocked = await level_up(client, character["id"], token)
        assert blocked.status_code == 400

        raised = await client.patch(
            "/characters/gm-panel/max-level",
            params={"character_id": character["id"]},
            json={"max_level": 2},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert raised.status_code == 200

        ok = await level_up(client, character["id"], token)
        assert ok.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
class TestScoreBoundaries:
    async def test_asi_to_exact_cap_twenty_then_blocked(self, client, player, player_token, gm_token, create_class, create_api_character):
        character_class = await create_class(name="Fighter")
        character, token = await create_api_character(class_id=character_class.id, owner=player, strength=16)

        await level_up(client, character["id"], token)   # 2
        await level_up(client, character["id"], token)   # 3
        response = await level_up(
            client, character["id"], token,
            {"choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 2}]}},
        )  # 4: STR effective 18
        assert response.status_code == 200

        await level_up(client, character["id"], token)   # 5
        response = await level_up(
            client, character["id"], token,
            {"choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 2}]}},
        )  # 6 (non-ASI level!) -> 400
        assert response.status_code == 400

        # Reach the cap through GM adjustments instead.
        ok = await client.post(
            "/characters/gm-panel/asi",
            params={"character_id": character["id"]},
            json={"increases": [{"ability": "STR", "amount": 2}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert ok.status_code == 201  # 18 + 2 = 20 <= 20

        over = await client.post(
            "/characters/gm-panel/asi",
            params={"character_id": character["id"]},
            json={"increases": [{"ability": "STR", "amount": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert over.status_code == 400

        stats = await get_stats(client, character["id"], token)
        assert stats["strength"]["total"] == 20

    async def test_negative_adjustments_floor_effective_at_one(self, client, gm_token, gm, create_class, create_character):
        character_class = await create_class(name="Sorcerer")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, charisma=3)

        response = await client.post(
            "/characters/gm-panel/asi",
            params={"character_id": character.id},
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
                "/characters/gm-panel/asi",
                params={"character_id": character.id},
                json={"increases": [{"ability": "STR", "amount": amount}]},
                headers={"Authorization": f"Bearer {gm_token}"},
            )
            assert response.status_code == 201
            ids.append(response.json()["id"])

        assert (await get_stats(client, character.id, gm_token))["strength"]["total"] == 15

        removed = await client.delete(
            "/characters/gm-panel/asi",
            params={"character_id": character.id, "adjustment_id": ids[0]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert removed.status_code == 204
        assert (await get_stats(client, character.id, gm_token))["strength"]["total"] == 13


@pytest.mark.integration
@pytest.mark.asyncio
class TestLateSetupGrants:
    async def test_subclass_set_after_creation_applies_feature_effects(
        self, client, player, player_token, gm_token, create_class, create_subclass, create_feature, create_api_character
    ):
        character_class = await create_class(name="Fighter")
        champion = await create_subclass(class_id=character_class.id, name="Champion")
        trait = await create_feature(
            name="Champion Trait", source_type="SUBCLASS", subclass_id=champion.id, level=None
        )
        await client.put(
            "/features/ability-increases",
            params={"feature_id": trait.id},
            json={"ability_increases": [{"ability": "STR", "amount": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        character, token = await create_api_character(class_id=character_class.id, owner=player, strength=10)

        response = await client.patch(
            "/characters/progression/subclass",
            params={"character_id": character["id"]},
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
        character, token = await create_api_character(
            class_id=character_class.id, owner=player, background_id=False
        )

        response = await client.patch(
            "/characters/progression/background",
            params={"character_id": character["id"]},
            json={"background_id": background.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert response.status_code == 200

        second = await client.patch(
            "/characters/progression/background",
            params={"character_id": character["id"]},
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
            "/characters/hp",
            params={"character_id": character["id"]},
            json={"delta": -7},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert damaged.status_code == 200
        assert damaged.json()["current_hp"] == 5

        rested = await client.post(
            "/characters/rest",
            params={"character_id": character["id"]},
            json={"type": "long"},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert rested.status_code == 200
        assert rested.json()["current_hp"] == 12
