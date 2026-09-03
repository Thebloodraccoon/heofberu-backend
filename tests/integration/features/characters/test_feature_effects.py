"""
Integration tests for fixed feature ability effects flowing into a
character's effective ability scores (and the per-ability cap).
"""

import pytest

from app.models.character_asi_choice_model import CharacterASIChoice, CharacterASIChoiceIncrease


async def set_feature_effects(client, gm_token, feature_id, increases):
    response = await client.put(
        f"/features/{feature_id}/ability-increases",
        json={"ability_increases": increases},
        headers={"Authorization": f"Bearer {gm_token}"},
    )
    assert response.status_code == 200, response.text


async def get_strength_total(client, character_id, token):
    """Effective STR from the player-facing stats view — always freshly computed, never the cache."""
    return await get_total(client, character_id, token, "strength")


async def get_total(client, character_id, token, ability):
    response = await client.get(
        f"/characters/{character_id}/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()[ability]["total"]


async def grant_feature(client, gm_token, character_id, feature_id):
    response = await client.post(
        f"/characters/{character_id}/gm-panel/features",
        json={"feature_id": feature_id},
        headers={"Authorization": f"Bearer {gm_token}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def adjust_asi(client, gm_token, character_id, increases):
    return await client.post(
        f"/characters/{character_id}/gm-panel/asi",
        json={"increases": increases},
        headers={"Authorization": f"Bearer {gm_token}"},
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestFeatureEffectsRefreshCachedDetail:
    async def test_editing_effects_refresh_cached_character_detail_immediately(
        self, client, player, player_token, gm_token, create_class, create_feature, create_api_character
    ):
        """GET /characters/{id} (Redis-cached detail) must not serve stale totals after an effects edit."""
        character_class = await create_class(name="Barbarian")
        primal_champion = await create_feature(
            name="Primal Champion", source_type="CLASS", class_id=character_class.id, level=1
        )
        character, token = await create_api_character(class_id=character_class.id)
        character_id = character["id"]

        await set_feature_effects(client, gm_token, primal_champion.id, [{"ability": "STR", "amount": 2}])

        first = await client.get(f"/characters/{character_id}", headers={"Authorization": f"Bearer {token}"})
        assert first.status_code == 200
        assert first.json()["ability_scores"]["strength_total"] == 12

        await set_feature_effects(client, gm_token, primal_champion.id, [{"ability": "STR", "amount": 4}])

        second = await client.get(f"/characters/{character_id}", headers={"Authorization": f"Bearer {token}"})
        assert second.status_code == 200
        assert second.json()["ability_scores"]["strength_total"] == 14


@pytest.mark.integration
@pytest.mark.asyncio
class TestFeatureEffectsInTotals:
    async def test_level_up_grants_class_feature_effect(
        self, client, player, player_token, gm_token, create_class, create_feature, create_api_character
    ):
        character_class = await create_class(name="Barbarian", hit_dice="D12")
        primal_champion = await create_feature(
            name="Primal Champion", source_type="CLASS", class_id=character_class.id, level=2
        )
        await set_feature_effects(
            client,
            gm_token,
            primal_champion.id,
            [
                {"ability": "STR", "amount": 4, "new_cap": 24},
                {"ability": "CON", "amount": 4, "new_cap": 24},
            ],
        )
        character, token = await create_api_character(class_id=character_class.id, owner=player, strength=15)
        assert await get_strength_total(client, character["id"], token) == 15

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert await get_strength_total(client, character["id"], token) == 19

    async def test_subclass_swap_removes_effect_immediately(
        self,
        client,
        gm_token,
        player,
        player_token,
        create_class,
        create_subclass,
        create_feature,
        create_api_character,
    ):
        character_class = await create_class(name="Fighter")
        champion = await create_subclass(class_id=character_class.id, name="Champion")
        battlemaster = await create_subclass(class_id=character_class.id, name="Battle Master")
        effect_feature = await create_feature(
            name="Improved Critical", source_type="SUBCLASS", subclass_id=champion.id, level=None
        )
        await set_feature_effects(client, gm_token, effect_feature.id, [{"ability": "STR", "amount": 2}])

        character, token = await create_api_character(
            class_id=character_class.id, owner=player, subclass_id=champion.id, strength=10
        )
        assert await get_strength_total(client, character["id"], token) == 12

        response = await client.patch(
            f"/characters/{character['id']}/progression/subclass",
            json={"subclass_id": battlemaster.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        # No self-heal delay: the swap itself refreshed the cache.
        assert await get_strength_total(client, character["id"], token) == 10

    async def test_gm_feature_grant_and_remove_refresh_cache(
        self, client, gm_token, gm, create_class, create_feature, create_character
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, charisma=10)
        curse = await create_feature(name="Cursed", source_type="OTHER")
        await set_feature_effects(client, gm_token, curse.id, [{"ability": "CHA", "amount": -3}])

        grant = await grant_feature(client, gm_token, character.id, curse.id)
        assert await get_total(client, character.id, gm_token, "charisma") == 7  # 10 - 3

        remove = await client.delete(
            f"/characters/{character.id}/gm-panel/features",
            params={"feature_id": grant["id"]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert remove.status_code == 204
        assert await get_total(client, character.id, gm_token, "charisma") == 10

    async def test_editing_reference_effects_refreshes_granted_characters(
        self, client, gm_token, gm, create_class, create_feature, create_character
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, wisdom=10)
        boon = await create_feature(name="Boon", source_type="OTHER")
        await set_feature_effects(client, gm_token, boon.id, [{"ability": "WIS", "amount": 1}])
        await grant_feature(client, gm_token, character.id, boon.id)
        assert await get_total(client, character.id, gm_token, "wisdom") == 11

        await set_feature_effects(client, gm_token, boon.id, [{"ability": "WIS", "amount": 3}])

        assert await get_total(client, character.id, gm_token, "wisdom") == 13

    async def test_high_level_character_gets_all_level_effects(
        self, client, player, player_token, gm_token, create_class, create_feature, create_api_character
    ):
        """A feature gated behind level 3 applies its effect the moment the level is reached."""

        character_class = await create_class(name="Fighter")
        late_boon = await create_feature(name="Late Boon", source_type="CLASS", class_id=character_class.id, level=3)
        await set_feature_effects(client, gm_token, late_boon.id, [{"ability": "CON", "amount": 2}])
        character, token = await create_api_character(class_id=character_class.id, owner=player, constitution=10)
        assert await get_total(client, character["id"], token, "constitution") == 10

        for _ in range(2):  # level 1 -> 3
            response = await client.post(
                f"/characters/{character['id']}/progression/level-up",
                json={},
                headers={"Authorization": f"Bearer {player_token}"},
            )
            assert response.status_code == 200

        assert await get_total(client, character["id"], token, "constitution") == 12

    async def test_con_effect_raises_default_level_up_hp_gain(
        self, client, player, player_token, gm_token, create_class, create_feature, create_api_character
    ):
        """The level-up CON modifier is derived from the EFFECTIVE total, feature effects included."""

        character_class = await create_class(name="Fighter", hit_dice="D10")
        toughness = await create_feature(name="Toughness", source_type="CLASS", class_id=character_class.id, level=None)
        await set_feature_effects(client, gm_token, toughness.id, [{"ability": "CON", "amount": 4}])
        # Effective CON = 14 + 4 = 18 -> modifier +4; starting max HP = die faces 10 + 4.
        character, token = await create_api_character(class_id=character_class.id, owner=player, constitution=14)
        assert character["max_hp"] == 14

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={},  # default average: half die (5) + 1 + CON mod (4) = 10
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["max_hp"] == 24


@pytest.mark.integration
@pytest.mark.asyncio
class TestPerAbilityCap:
    async def test_gm_panel_can_raise_to_thirty_without_a_feature(
        self, client, gm_token, gm, create_class, create_character
    ):
        """The GM panel is its own ceiling: it can take an ability up to 30 with NO feature required."""
        character_class = await create_class(name="Barbarian")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, strength=10)

        to_thirty = await adjust_asi(client, gm_token, character.id, [{"ability": "STR", "amount": 20}])
        assert to_thirty.status_code == 201  # 10 + 20 = 30

        over_thirty = await adjust_asi(client, gm_token, character.id, [{"ability": "STR", "amount": 1}])
        assert over_thirty.status_code == 400  # 31 > 30

    async def test_new_cap_above_thirty_rejected_with_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Over 9000", source_type="OTHER")

        response = await client.put(
            f"/features/{feature.id}/ability-increases",
            json={"ability_increases": [{"ability": "STR", "amount": 4, "new_cap": 31}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_new_cap_below_twenty_rejected_with_422(self, client, gm_token, create_feature):
        feature = await create_feature(name="Under Twenty", source_type="OTHER")

        response = await client.put(
            f"/features/{feature.id}/ability-increases",
            json={"ability_increases": [{"ability": "STR", "amount": 1, "new_cap": 19}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        assert response.status_code == 422

    async def test_player_level_up_asi_is_capped_at_twenty_even_with_new_cap_30(
        self, client, player, player_token, gm_token, create_class, create_feature, create_api_character
    ):
        """A player's own ASI choice may never push an ability past 20 — even if a feature raised the cap to 30."""
        character_class = await create_class(name="Fighter", hit_dice="D10")
        primal_champion = await create_feature(name="Primal Champion", source_type="OTHER")
        await set_feature_effects(
            client,
            gm_token,
            primal_champion.id,
            [{"ability": "STR", "amount": 4, "new_cap": 30}],
        )
        character, token = await create_api_character(
            class_id=character_class.id, owner=player, strength=18
        )
        await grant_feature(client, gm_token, character["id"], primal_champion.id)
        # Effective STR is already 22 (feature-driven, above 20). cap is 30.

        for _ in (2, 3):  # level up to 3 (no ASI)
            response = await client.post(
                f"/characters/{character['id']}/progression/level-up",
                json={},
                headers={"Authorization": f"Bearer {player_token}"},
            )
            assert response.status_code == 200

        # Level 4 ASI: +2 STR would push to 24 > 20 -> player is capped at 20.
        rejected = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={"choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 2}]}},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert rejected.status_code == 400

    async def test_feature_effect_raises_effective_score_above_twenty(
        self, client, gm_token, gm, create_class, create_feature, create_character
    ):
        """A granted feature's amount lifts the effective score above 20 (up to its 30 new_cap)."""
        character_class = await create_class(name="Barbarian")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, strength=18)
        primal_champion = await create_feature(name="Primal Champion", source_type="OTHER")
        await set_feature_effects(
            client,
            gm_token,
            primal_champion.id,
            [{"ability": "STR", "amount": 4, "new_cap": 30}],
        )
        await grant_feature(client, gm_token, character.id, primal_champion.id)

        # Feature-driven total: 18 base + 4 feature = 22 (> 20), allowed.
        assert await get_strength_total(client, character.id, gm_token) == 22

    async def test_gm_feat_grant_does_not_enforce_ability_score_cap(
        self, client, gm_token, gm, create_class, create_feat, create_feature, create_character
    ):
        """GM-feat cap enforcement is no longer checked server-side."""
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, strength=19)
        primal_champion = await create_feature(name="Primal Champion", source_type="OTHER")
        await set_feature_effects(
            client,
            gm_token,
            primal_champion.id,
            [{"ability": "STR", "amount": 0, "new_cap": 30}],
        )
        await grant_feature(client, gm_token, character.id, primal_champion.id)

        feat = await create_feat(name="Mighty")
        asi_response = await client.put(
            f"/feats/{feat.id}/ability-score-increases",
            json={"ability_score_increases": [{"ability": "STR", "amount": 2}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        feat_asi_id = asi_response.json()["ability_score_increases"][0]["id"]

        granted = await client.post(
            f"/characters/{character.id}/gm-panel/feats",
            json={"feat_id": feat.id, "ability_score_increase_id": feat_asi_id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert granted.status_code == 201

    async def test_combined_sources_stack_in_one_total(
        self, client, gm_token, gm, player_token, create_class, create_feat, create_feature, create_character
    ):
        """Feat ASI + counted log ASI + feature effect stack onto the same total."""
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, strength=10)

        # Feat with an ASI choice (+1 STR).
        feat = await create_feat(name="Resilient")
        asi_response = await client.put(
            f"/feats/{feat.id}/ability-score-increases",
            json={"ability_score_increases": [{"ability": "STR", "amount": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        feat_asi_id = asi_response.json()["ability_score_increases"][0]["id"]
        grant_response = await client.post(
            f"/characters/{character.id}/gm-panel/feats",
            json={"feat_id": feat.id, "ability_score_increase_id": feat_asi_id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_response.status_code == 201

        # Counted log ASI (+2 STR).
        log_response = await adjust_asi(client, gm_token, character.id, [{"ability": "STR", "amount": 2}])
        assert log_response.status_code == 201

        # Feature effect (+1 STR).
        boon = await create_feature(name="Boon of Strength", source_type="OTHER")
        await set_feature_effects(client, gm_token, boon.id, [{"ability": "STR", "amount": 1}])
        await grant_feature(client, gm_token, character.id, boon.id)

        # 10 base + 1 feat + 2 log + 1 feature.
        assert await get_strength_total(client, character.id, gm_token) == 14


@pytest.mark.integration
@pytest.mark.asyncio
class TestLegacyGrandfatheredChoices:
    async def test_legacy_row_is_not_counted(self, db_session, client, gm_token, gm, create_class, create_character):
        """
        Pre-rework rows had their points baked into the base columns and
        carry applied_to_base=True — the calculator must not count them
        again (16 base stays 16, never 18).
        """

        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, strength=16)
        legacy_choice = CharacterASIChoice(
            character_id=character.id,
            class_level=4,
            choice_type="ASI",
            applied_to_base=True,
        )
        db_session.add(legacy_choice)
        await db_session.flush()
        db_session.add(CharacterASIChoiceIncrease(character_asi_choice_id=legacy_choice.id, ability="STR", amount=2))
        await db_session.commit()

        assert await get_strength_total(client, character.id, gm_token) == 16

    async def test_counted_row_applies_once(self, db_session, client, gm_token, gm, create_class, create_character):
        """A modern row (applied_to_base=False) IS counted."""

        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=gm.id, class_id=character_class.id, strength=14)
        choice = CharacterASIChoice(
            character_id=character.id,
            class_level=4,
            choice_type="ASI",
            applied_to_base=False,
        )
        db_session.add(choice)
        await db_session.flush()
        db_session.add(CharacterASIChoiceIncrease(character_asi_choice_id=choice.id, ability="STR", amount=2))
        await db_session.commit()

        assert await get_strength_total(client, character.id, gm_token) == 16
