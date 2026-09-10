"""Tests for character progression endpoints: late background setup, subclass/subrace setup, leveling up, rebuild."""

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
class TestRebuild:
    async def test_owner_can_rebuild_recomputing_derived_state_and_preserving_untouched_fields(
        self,
        client,
        player,
        player_token,
        gm_token,
        create_class,
        create_race,
        create_skill,
        create_spell,
        create_item,
        create_api_character,
    ):
        wizard = await create_class(name="Wizard", hit_dice="D6", spellcasting_ability="INT")
        await set_class_spell_slots(client, gm_token, wizard, 1, [{"spell_level": "LEVEL_1", "slots": 2}])
        fighter = await create_class(name="Fighter", hit_dice="D10")
        fighter_skill = await create_skill(key="ATHLETICS", name="Athletics", ability="STR")
        skills_response = await client.put(
            f"/classes/{fighter.id}/available-skills",
            json={"skill_ids": [fighter_skill.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert skills_response.status_code == 200, skills_response.text

        human = await create_race(name="Human")
        elf = await create_race(name="Elf")

        character, _ = await create_api_character(
            class_id=wizard.id,
            owner=player,
            race_id=human.id,
            strength=8,
            dexterity=10,
            constitution=12,
            intelligence=16,
            wisdom=10,
            charisma=8,
        )

        spell = await create_spell(name="Magic Missile", level="LEVEL_1")
        spell_response = await client.post(
            f"/characters/{character['id']}/spells",
            json={"spell_id": spell.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert spell_response.status_code == 201, spell_response.text

        notes_response = await client.patch(
            f"/characters/{character['id']}",
            json={"notes": "Keep me"},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert notes_response.status_code == 200, notes_response.text

        backstory_response = await client.put(
            f"/characters/{character['id']}/backstory",
            json={"content": "A long tale."},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert backstory_response.status_code == 200, backstory_response.text

        item = await create_item(name="Rope")
        item_response = await client.post(
            f"/characters/{character['id']}/gm-panel/items",
            json={"item_id": item.id, "quantity": 1},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert item_response.status_code == 201, item_response.text

        # Fighter D10 + CON 14 (mod +2) at level 1 fixes max_hp at exactly 12.
        response = await client.post(
            f"/characters/{character['id']}/rebuild",
            json={
                "class_id": fighter.id,
                "race_id": elf.id,
                "strength": 16,
                "dexterity": 12,
                "constitution": 14,
                "intelligence": 8,
                "wisdom": 10,
                "charisma": 10,
                "max_hp": 12,
                "skill_ids": [fighter_skill.id],
                "asi_choices": [],
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200, response.text
        rebuilt = response.json()
        assert rebuilt["class_id"] == fighter.id
        assert rebuilt["race_id"] == elf.id
        assert rebuilt["max_hp"] == 12
        assert rebuilt["current_hp"] == 12
        assert rebuilt["temp_hp"] == 0

        rebuilt_proficiencies = await client.get(
            f"/characters/{character['id']}/proficiencies", headers={"Authorization": f"Bearer {player_token}"}
        )
        assert [row["skill_id"] for row in rebuilt_proficiencies.json()["skills"]] == [fighter_skill.id]
        # Untouched by the rebuild:
        assert rebuilt["notes"] == "Keep me"

        spells_response = await client.get(
            f"/characters/{character['id']}/spells",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert spells_response.status_code == 200, spells_response.text
        assert spells_response.json()["spells"] == []

        backstory_check = await client.get(
            f"/characters/{character['id']}/backstory",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert backstory_check.json()["content"] == "A long tale."

        items_check = await client.get(
            f"/characters/{character['id']}/items",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert any(row["item"]["name"] == "Rope" for row in items_check.json())

    async def test_rebuild_rejects_max_hp_outside_the_new_range(
        self, client, player, player_token, create_class, create_race, create_api_character
    ):
        fighter = await create_class(name="Fighter", hit_dice="D10")
        elf = await create_race(name="Elf")
        character, _ = await create_api_character(class_id=fighter.id, owner=player, race_id=elf.id)

        response = await client.post(
            f"/characters/{character['id']}/rebuild",
            json={
                "class_id": fighter.id,
                "race_id": elf.id,
                "strength": 10,
                "dexterity": 10,
                "constitution": 10,
                "intelligence": 10,
                "wisdom": 10,
                "charisma": 10,
                "max_hp": 999,
                "asi_choices": [],
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_rebuild_requires_asi_choices_for_reached_levels(
        self, client, player, player_token, create_class, create_race, create_api_character
    ):
        fighter = await create_class(name="Fighter", hit_dice="D10")
        elf = await create_race(name="Elf")
        character, token = await create_api_character(class_id=fighter.id, owner=player, race_id=elf.id)
        await level_up_to(client, token, character["id"], 3)
        level_up_response = await client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={"choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 2}]}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert level_up_response.status_code == 200, level_up_response.text

        response = await client.post(
            f"/characters/{character['id']}/rebuild",
            json={
                "class_id": fighter.id,
                "race_id": elf.id,
                "strength": 10,
                "dexterity": 10,
                "constitution": 10,
                "intelligence": 10,
                "wisdom": 10,
                "charisma": 10,
                "max_hp": 40,
                "asi_choices": [],
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_rebuild_without_race_id_is_rejected(
        self, client, player, player_token, create_class, create_api_character
    ):
        fighter = await create_class(name="Fighter", hit_dice="D10")
        character, _ = await create_api_character(class_id=fighter.id, owner=player)

        response = await client.post(
            f"/characters/{character['id']}/rebuild",
            json={
                "class_id": fighter.id,
                "strength": 10,
                "dexterity": 10,
                "constitution": 10,
                "intelligence": 10,
                "wisdom": 10,
                "charisma": 10,
                "max_hp": 10,
                "asi_choices": [],
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 422

    async def test_player_cannot_rebuild_other_players_character(
        self, client, player_token, create_user, create_class, create_race, create_character
    ):
        character_class = await create_class(name="Fighter")
        race = await create_race(name="Human")
        other = await create_user(username="other", email="other@example.com")
        character = await create_character(owner_id=other.id, class_id=character_class.id, race_id=race.id)

        response = await client.post(
            f"/characters/{character.id}/rebuild",
            json={
                "class_id": character_class.id,
                "race_id": race.id,
                "strength": 10,
                "dexterity": 10,
                "constitution": 10,
                "intelligence": 10,
                "wisdom": 10,
                "charisma": 10,
                "max_hp": 10,
                "asi_choices": [],
            },
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
            f"/characters/{character['id']}/stats",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert stats_response.status_code == 200
        assert stats_response.json()["strength"] == {
            "base": 14,
            "total": 16,
            "contributions": [{"source": "asi", "label": "Level 4 (ASI)", "amount": 2}],
        }

    async def test_feat_choice_with_asi_options_without_choice_is_rejected(
        self,
        client,
        player,
        player_token,
        gm_token,
        create_class,
        create_api_character,
        create_feat,
    ):
        """A feat offering an ASI choice group must have it resolved — level-up never grants it half-picked."""
        character_class = await create_class(name="Fighter", hit_dice="D10")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        await level_up_to(client, player_token, character["id"], target_level=3)
        feat = await create_feat(name="Resilient")
        await client.put(
            f"/feats/{feat.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "label": "Ability Score Increase",
                        "options": [{"label": "STR", "ability_effects": [{"ability": "STR", "amount": 1}]}],
                    }
                ]
            },
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
            f"/feats/{feat.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "label": "Ability Score Increase",
                        "options": [{"label": "STR", "ability_effects": [{"ability": "STR", "amount": 1}]}],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert asi_response.status_code == 200
        asi_id = asi_response.json()[0]["options"][0]["ability_effects"][0]["id"]

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


@pytest.mark.integration
@pytest.mark.asyncio
class TestLevelUpFeatureChoices:
    """Level-up must resolve the choice groups of newly granted features via `feature_choices`."""

    async def _feature_with_skill_choice(self, client, gm_token, create_feature, create_skill, class_id):
        """Create a CLASS feature at level 3 carrying a "pick one skill" choice group; return ids."""
        skill = await create_skill(key="ATHLETICS", name="Athletics", ability="STR")
        feature = await create_feature(
            name="Skill Reader", source_type="CLASS", class_id=class_id, level=3
        )
        choice_response = await client.put(
            f"/features/{feature.id}/choice-groups",
            json={
                "choice_groups": [
                    {
                        "pick_count": 1,
                        "label": "Pick a skill",
                        "options": [{"label": "Athletics", "skill_effects": [{"skill_id": skill.id}]}],
                    }
                ]
            },
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert choice_response.status_code == 200, choice_response.text
        effects = (await client.get(f"/features/{feature.id}/effects")).json()
        group_id = effects["choice_groups"][0]["id"]
        option_id = effects["choice_groups"][0]["options"][0]["id"]
        return feature, skill, group_id, option_id

    async def test_level_up_2_to_3_without_feature_choices_returns_422_and_rolls_back(
        self, client, player, player_token, gm_token, create_class, create_api_character, create_feature, create_skill
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        _, _, _, _ = await self._feature_with_skill_choice(
            client, gm_token, create_feature, create_skill, character_class.id
        )
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        character_id = character["id"]

        await level_up_to(client, player_token, character_id, target_level=2)

        response = await client.post(
            f"/characters/{character_id}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 422
        refreshed = await client.get(
            f"/characters/{character_id}",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert refreshed.status_code == 200
        assert refreshed.json()["level"] == 2

    async def test_level_up_with_feature_choices_materializes_the_pick(
        self, client, player, player_token, gm_token, create_class, create_api_character, create_feature, create_skill
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        feature, skill, group_id, option_id = await self._feature_with_skill_choice(
            client, gm_token, create_feature, create_skill, character_class.id
        )
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        character_id = character["id"]

        await level_up_to(client, player_token, character_id, target_level=2)

        response = await client.post(
            f"/characters/{character_id}/progression/level-up",
            json={
                "feature_choices": [
                    {
                        "feature_id": feature.id,
                        "choice_group_id": group_id,
                        "choice_option_id": option_id,
                    }
                ]
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200, response.text
        assert response.json()["level"] == 3

        refreshed = await client.get(
            f"/characters/{character_id}",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert refreshed.json()["level"] == 3

        refreshed_proficiencies = await client.get(
            f"/characters/{character_id}/proficiencies", headers={"Authorization": f"Bearer {player_token}"}
        )
        assert skill.id in [item["skill_id"] for item in refreshed_proficiencies.json()["skills"]]

    async def test_feature_choices_for_unrelated_feature_are_ignored(
        self, client, player, player_token, gm_token, create_class, create_api_character, create_feature, create_skill
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        _, _, group_id, option_id = await self._feature_with_skill_choice(
            client, gm_token, create_feature, create_skill, character_class.id
        )
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        character_id = character["id"]

        # Level 1 -> 2 unlocks nothing at level 2; a feature_choices entry
        # naming the level-3 feature (not granted yet) must be ignored.
        response = await client.post(
            f"/characters/{character_id}/progression/level-up",
            json={
                "feature_choices": [
                    {
                        "feature_id": 999999,
                        "choice_group_id": group_id,
                        "choice_option_id": option_id,
                    }
                ]
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200, response.text
        assert response.json()["level"] == 2

    async def test_two_granted_features_both_need_answers(
        self, client, player, player_token, gm_token, create_class, create_api_character, create_feature, create_skill
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        skill_a = await create_skill(key="ATHLETICS", name="Athletics", ability="STR")
        skill_b = await create_skill(key="PERCEPTION", name="Perception", ability="WIS")
        skill_a_id = skill_a.id
        skill_b_id = skill_b.id
        feat_a = await create_feature(name="Feature A", source_type="CLASS", class_id=character_class.id, level=3)
        feat_b = await create_feature(name="Feature B", source_type="CLASS", class_id=character_class.id, level=3)
        feat_a_id = feat_a.id
        feat_b_id = feat_b.id

        def _configure_feature(feature_id, skill_id):
            response = client.put(
                f"/features/{feature_id}/choice-groups",
                json={
                    "choice_groups": [
                        {
                            "pick_count": 1,
                            "options": [{"label": "Pick", "skill_effects": [{"skill_id": skill_id}]}],
                        }
                    ]
                },
                headers={"Authorization": f"Bearer {gm_token}"},
            )
            return response

        resp_a = await _configure_feature(feat_a_id, skill_a_id)
        assert resp_a.status_code == 200, resp_a.text
        resp_b = await _configure_feature(feat_b_id, skill_b_id)
        assert resp_b.status_code == 200, resp_b.text
        effects_a = (await client.get(f"/features/{feat_a_id}/effects")).json()
        effects_b = (await client.get(f"/features/{feat_b_id}/effects")).json()
        group_a = effects_a["choice_groups"][0]["id"]
        option_a = effects_a["choice_groups"][0]["options"][0]["id"]
        group_b = effects_b["choice_groups"][0]["id"]
        option_b = effects_b["choice_groups"][0]["options"][0]["id"]

        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        character_id = character["id"]
        await level_up_to(client, player_token, character_id, target_level=2)

        # Only covering the first feature leaves the second unanswered -> 422 + rollback.
        partial = await client.post(
            f"/characters/{character_id}/progression/level-up",
            json={
                "feature_choices": [
                    {
                        "feature_id": feat_a_id,
                        "choice_group_id": group_a,
                        "choice_option_id": option_a,
                    }
                ]
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert partial.status_code == 422
        refreshed = await client.get(
            f"/characters/{character_id}",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert refreshed.json()["level"] == 2

        # Covering both succeeds and materializes both picks.
        full = await client.post(
            f"/characters/{character_id}/progression/level-up",
            json={
                "feature_choices": [
                    {
                        "feature_id": feat_a_id,
                        "choice_group_id": group_a,
                        "choice_option_id": option_a,
                    },
                    {
                        "feature_id": feat_b_id,
                        "choice_group_id": group_b,
                        "choice_option_id": option_b,
                    },
                ]
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert full.status_code == 200, full.text
        refreshed = await client.get(
            f"/characters/{character_id}/proficiencies",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        skill_ids = {item["skill_id"] for item in refreshed.json()["skills"]}
        assert skill_a_id in skill_ids
        assert skill_b_id in skill_ids

    async def test_feature_without_choice_groups_needs_no_feature_choices(
        self, client, player, player_token, gm_token, create_class, create_api_character, create_feature
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        feature = await create_feature(
            name="Fixed Boon", source_type="CLASS", class_id=character_class.id, level=3
        )
        await client.put(
            f"/features/{feature.id}/effects",
            json={"ability_effects": [{"ability": "STR", "amount": 2}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        character, _ = await create_api_character(class_id=character_class.id, owner=player, strength=10)
        character_id = character["id"]
        await level_up_to(client, player_token, character_id, target_level=2)

        response = await client.post(
            f"/characters/{character_id}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200, response.text
        assert response.json()["level"] == 3
        stats = await client.get(
            f"/characters/{character_id}/stats",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert stats.status_code == 200
        assert stats.json()["strength"]["total"] == 12
