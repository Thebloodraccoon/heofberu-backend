"""Tests for character progression endpoints: late background setup, subclass/subrace setup, leveling up, rebuild stub."""

import pytest


async def set_class_spell_slots(client, gm_token, character_class, class_level, slots):
    """Set a class's spell slot progression for a level via the API (GM only)."""
    response = await client.put(
        f"/classes/{character_class.id}/spell-slots",
        params={"class_level": class_level},
        json={"slots": slots},
        headers={"Authorization": f"Bearer {gm_token}"},
    )
    assert response.status_code == 200, response.text
    return character_class


async def level_up_to(client, token, character_id, target_level):
    """
    Plain level-ups (default HP gain, no choices) until ``target_level``.

    Only safe while the path never crosses an ASI level (the first is
    level 4), since those require an explicit choice payload.
    """
    for _ in range(target_level - 1):
        response = await client.post(
            f"/characters/{character_id}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestBackgroundSetup:
    async def test_owner_can_set_background_when_none_and_grants_follow(
        self, client, player, player_token, create_class, create_api_character, create_background
    ):
        character_class = await create_class(name="Fighter")
        character, _ = await create_api_character(class_id=character_class.id, owner=player, background_id=False)
        assert character["background_id"] is None

        background = await create_background(name="Sage")

        response = await client.patch(
            f"/characters/{character['id']}/progression/background",
            json={"background_id": background.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["background_id"] == background.id

    async def test_setting_background_when_already_set_returns_409(
        self, client, player, player_token, create_class, create_api_character, create_background
    ):
        character_class = await create_class(name="Fighter")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        other_background = await create_background(name="Sage")

        response = await client.patch(
            f"/characters/{character['id']}/progression/background",
            json={"background_id": other_background.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 409

    async def test_unknown_background_returns_404(
        self, client, player, player_token, create_class, create_api_character
    ):
        character_class = await create_class(name="Fighter")
        character, _ = await create_api_character(class_id=character_class.id, owner=player, background_id=False)

        response = await client.patch(
            f"/characters/{character['id']}/progression/background",
            json={"background_id": 999999},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 404

    async def test_player_cannot_set_other_players_character_background(
        self, client, player_token, create_user, create_class, create_character, create_background
    ):
        character_class = await create_class(name="Fighter")
        other = await create_user(username="other", email="other@example.com")
        character = await create_character(owner_id=other.id, class_id=character_class.id)
        background = await create_background(name="Sage")

        response = await client.patch(
            f"/characters/{character.id}/progression/background",
            json={"background_id": background.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestRebuildStub:
    async def test_rebuild_returns_501_until_implemented(
        self, client, player, player_token, create_class, create_api_character
    ):
        character_class = await create_class(name="Fighter")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        response = await client.post(
            f"/characters/{character['id']}/rebuild",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 501

    async def test_player_cannot_rebuild_other_players_character(
        self, client, player_token, create_user, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        other = await create_user(username="other", email="other@example.com")
        character = await create_character(owner_id=other.id, class_id=character_class.id)

        response = await client.post(
            f"/characters/{character.id}/rebuild",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestSubclassChange:
    async def test_owner_can_set_subclass(
        self, client, player, player_token, create_class, create_subclass, create_api_character
    ):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        response = await client.patch(
            f"/characters/{character['id']}/progression/subclass",
            json={"subclass_id": subclass.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["subclass_id"] == subclass.id

    async def test_owner_can_clear_subclass(
        self, client, player, player_token, create_class, create_subclass, create_api_character
    ):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")
        character, _ = await create_api_character(class_id=character_class.id, owner=player, subclass_id=subclass.id)

        response = await client.patch(
            f"/characters/{character['id']}/progression/subclass",
            json={"subclass_id": None},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["subclass_id"] is None

    async def test_subclass_of_another_class_returns_404(
        self, client, player, player_token, create_class, create_subclass, create_api_character
    ):
        fighter = await create_class(name="Fighter")
        wizard = await create_class(name="Wizard", hit_dice="D6", spellcasting_ability="INT")
        wizard_subclass = await create_subclass(class_id=wizard.id, name="School of Evocation")
        character, _ = await create_api_character(class_id=fighter.id, owner=player)

        response = await client.patch(
            f"/characters/{character['id']}/progression/subclass",
            json={"subclass_id": wizard_subclass.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 404

    async def test_unknown_subclass_returns_404(self, client, player, player_token, create_class, create_api_character):
        character_class = await create_class(name="Fighter")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        response = await client.patch(
            f"/characters/{character['id']}/progression/subclass",
            json={"subclass_id": 999999},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 404

    async def test_player_cannot_change_other_players_character_subclass(
        self, client, player_token, create_user, create_class, create_subclass, create_character
    ):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")
        other = await create_user(username="other", email="other@example.com")
        character = await create_character(owner_id=other.id, class_id=character_class.id)

        response = await client.patch(
            f"/characters/{character.id}/progression/subclass",
            json={"subclass_id": subclass.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestLevelUp:
    async def test_non_asi_level_up_applies_default_hp_gain(
        self, client, player, player_token, create_class, create_api_character
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["level"] == 2
        assert body["max_hp"] == 16

    async def test_default_hp_gain_never_drops_below_one(
        self, client, player, player_token, create_caster_class, create_api_character
    ):
        """A d6 class with CON 3 (modifier -4) would compute 3+1-4=0 — the 5e minimum of 1 HP applies."""

        character_class = await create_caster_class(name="Squishy")
        character, _ = await create_api_character(class_id=character_class.id, owner=player, constitution=3)
        assert character["max_hp"] == 2  # starting: die faces 6 + (-4), clamped to >= 1

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["level"] == 2
        assert body["max_hp"] == 3  # default gain 0 -> clamped to the 1 HP minimum

    async def test_level_up_with_custom_hp_gain(self, client, player, player_token, create_class, create_api_character):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={"hit_points_gained": 8},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["max_hp"] == 18

    async def test_hp_gain_outside_hit_die_range_returns_400(
        self, client, player, player_token, create_class, create_api_character
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={"hit_points_gained": 11},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_choice_at_non_asi_level_returns_400(
        self, client, player, player_token, create_class, create_api_character
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={"choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 1}]}},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_asi_level_requires_a_choice(self, client, player, player_token, create_class, create_api_character):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        await level_up_to(client, player_token, character["id"], target_level=3)

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_asi_level_up_applies_increases_and_records_choice(
        self, client, player, player_token, create_class, create_api_character
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        character, _ = await create_api_character(class_id=character_class.id, owner=player, strength=14)
        await level_up_to(client, player_token, character["id"], target_level=3)

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={"choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 2}]}},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["level"] == 4
        assert body["ability_scores"]["strength_total"] == 16

        choices_response = await client.get(
            f"/characters/{character['id']}/progression/asi-choices",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert choices_response.status_code == 200
        choices = choices_response.json()
        # Only the level-4 ASI choice is recorded.
        assert len(choices) == 1
        level_choice = choices[0]
        assert level_choice["class_level"] == 4
        assert level_choice["choice_type"] == "ASI"
        assert level_choice["increases"] == [{"ability": "STR", "amount": 2}]

        # The base columns stay at their originally entered values; the
        # counted points live in the ASI-choice log and lift only the total.
        stats_response = await client.get(
            f"/characters/{character['id']}/gm-panel/stats",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert stats_response.status_code == 200
        assert stats_response.json()["strength"] == {"base": 14, "total": 16}

    async def test_feat_choice_with_asi_options_without_choice_returns_422(
        self,
        client,
        player,
        player_token,
        gm_token,
        create_class,
        create_api_character,
        create_feat,
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        await level_up_to(client, player_token, character["id"], target_level=3)
        feat = await create_feat(name="Resilient")
        await client.put(
            f"/feats/{feat.id}/ability-score-increases",
            json={"ability_score_increases": [{"ability": "STR", "amount": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={"choice": {"type": "FEAT", "feat_id": feat.id}},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 422

    async def test_asi_above_score_cap_returns_400(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        character = await create_character(owner_id=player.id, class_id=character_class.id, level=3, strength=19)

        response = await client.post(
            f"/characters/{character.id}/progression/level-up",
            json={"choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 2}]}},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_feat_choice_grants_feat_and_records_choice(
        self, client, player, player_token, create_class, create_api_character, create_feat
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        await level_up_to(client, player_token, character["id"], target_level=3)
        feat = await create_feat(name="Alert")

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={"choice": {"type": "FEAT", "feat_id": feat.id}},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["level"] == 4

        feats_response = await client.get(
            f"/characters/{character['id']}/feats",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        feats = feats_response.json()
        # Only the level-up feat is granted.
        assert len(feats) == 1
        assert feat.id in [item["feat_id"] for item in feats]

        choices_response = await client.get(
            f"/characters/{character['id']}/progression/asi-choices",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        choices = choices_response.json()
        assert len(choices) == 1
        level_choice = choices[0]
        assert level_choice["class_level"] == 4
        assert level_choice["choice_type"] == "FEAT"
        assert level_choice["feat_id"] == feat.id

    async def test_feat_choice_with_unknown_feat_returns_404(
        self, client, player, player_token, create_class, create_api_character
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        await level_up_to(client, player_token, character["id"], target_level=3)

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={"choice": {"type": "FEAT", "feat_id": 999999}},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 404

    async def test_feat_choice_already_known_returns_409(
        self, client, player, player_token, gm_token, create_class, create_api_character, create_feat
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        await level_up_to(client, player_token, character["id"], target_level=3)
        feat = await create_feat(name="Alert")

        grant_response = await client.post(
            f"/characters/{character['id']}/gm-panel/feats",
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert grant_response.status_code == 201

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={"choice": {"type": "FEAT", "feat_id": feat.id}},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 409

    async def test_feat_choice_with_asi_increase_applies_bonus(
        self,
        client,
        player,
        player_token,
        gm_token,
        create_class,
        create_api_character,
        create_feat,
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        character, _ = await create_api_character(class_id=character_class.id, owner=player, strength=13)
        await level_up_to(client, player_token, character["id"], target_level=3)
        feat = await create_feat(name="Resilient")
        asi_response = await client.put(
            f"/feats/{feat.id}/ability-score-increases",
            json={"ability_score_increases": [{"ability": "STR", "amount": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert asi_response.status_code == 200
        asi_id = asi_response.json()["ability_score_increases"][0]["id"]

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={
                "choice": {
                    "type": "FEAT",
                    "feat_id": feat.id,
                    "ability_score_increase_id": asi_id,
                }
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["ability_scores"]["strength_total"] == 14

    async def test_level_up_reapplies_spell_slot_progression(
        self, client, player, player_token, gm_token, create_caster_class, create_api_character
    ):
        character_class = await create_caster_class(name="Wizard")
        await set_class_spell_slots(
            client,
            gm_token,
            character_class,
            2,
            [{"spell_level": "LEVEL_1", "slots": 3}],
        )
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        slots_response = await client.get(
            f"/characters/{character['id']}/spells",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        slots = {item["spell_level"]: item for item in slots_response.json()["spell_slots"]}
        assert slots["LEVEL_1"]["total"] == 3

    async def test_level_up_at_max_level_returns_400(
        self, client, player, player_token, create_class, create_character
    ):
        """Level is capped at 20; a max-level character cannot level up again."""
        character_class = await create_class(name="Fighter", hit_dice="D10")
        character = await create_character(owner_id=player.id, class_id=character_class.id, level=20)

        response = await client.post(
            f"/characters/{character.id}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_player_cannot_level_up_other_players_character(
        self, client, player_token, create_user, create_class, create_character
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        other = await create_user(username="other", email="other@example.com")
        character = await create_character(owner_id=other.id, class_id=character_class.id)

        response = await client.post(
            f"/characters/{character.id}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestASIChoices:
    async def test_new_character_has_no_choices(self, client, player, player_token, create_class, create_api_character):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        response = await client.get(
            f"/characters/{character['id']}/progression/asi-choices",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json() == []

    async def test_asi_choices_accumulate_across_levels(
        self, client, player, player_token, create_class, create_api_character, create_feat
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        feat = await create_feat(name="Alert")

        for class_level in range(2, 9):
            if class_level == 8:
                payload = {"choice": {"type": "FEAT", "feat_id": feat.id}}
            elif class_level == 4:
                payload = {"choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 1}]}}
            else:
                payload = {}
            response = await client.post(
                f"/characters/{character['id']}/progression/level-up",
                json=payload,
                headers={"Authorization": f"Bearer {player_token}"},
            )
            assert response.status_code == 200, response.text

        response = await client.get(
            f"/characters/{character['id']}/progression/asi-choices",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        choices = response.json()
        # The level-4 ASI + the level-8 FEAT, ordered by class level.
        assert [choice["class_level"] for choice in choices] == [4, 8]
        assert [choice["choice_type"] for choice in choices] == ["ASI", "FEAT"]

    async def test_player_cannot_view_other_players_asi_choices(
        self, client, player_token, create_user, create_class, create_character
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        other = await create_user(username="other", email="other@example.com")
        character = await create_character(owner_id=other.id, class_id=character_class.id)

        response = await client.get(
            f"/characters/{character.id}/progression/asi-choices",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
