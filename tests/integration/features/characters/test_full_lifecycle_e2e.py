"""
One long end-to-end lifecycle: register/login, build the catalog (class,
spells, feats), create a character, level up to 8 with a FEAT choice and an
ASI choice along the way, late-set subclass/subrace/background, equip items,
learn spells, exercise GM-panel feat/ASI writes including the score-20 cap,
and finally assert GET /characters/{id} is consistent with the rules
(HP floor of 1 per level, ASI counted from child rows, expertise toggle).
"""

import pytest

PASSWORD = "correct-horse-battery"


@pytest.mark.integration
@pytest.mark.asyncio
class TestFullCharacterLifecycle:
    async def test_register_to_level_eight_lifecycle(
        self,
        client,
        gm_token,
        create_skill,
        create_race,
        create_subrace,
        create_background,
        create_item,
        create_spell,
    ):
        register_response = await client.post(
            "/auth/register",
            json={"username": "aria_of_the_vale", "email": "aria@example.com", "password": PASSWORD},
        )
        assert register_response.status_code == 201, register_response.text
        register_body = register_response.json()
        token = register_body["access_token"]
        player_headers = {"Authorization": f"Bearer {token}"}

        login_response = await client.post("/auth/login", json={"email": "aria@example.com", "password": PASSWORD})
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        player_headers = {"Authorization": f"Bearer {token}"}

        skill = await create_skill(key="ARCANA", name="Arcana", ability="INT")
        race = await create_race(name="Human")
        subrace = await create_subrace(race_id=race.id, name="Illuskan")
        background = await create_background(name="Sage")
        longsword = await create_item(name="Longsword", item_type="WEAPON")
        potion = await create_item(name="Healing Potion", item_type="POTION")

        gm_headers = {"Authorization": f"Bearer {gm_token}"}
        class_response = await client.post(
            "/classes",
            json={
                "name": "Battle Mage",
                "hit_dice": "D10",
                "spellcasting_ability": "INT",
                "saving_throws": ["STR", "CON"],
                "armor_proficiencies": ["LIGHT"],
                "weapon_proficiencies": ["MARTIAL"],
                "available_skills": [skill.id],
            },
            headers=gm_headers,
        )
        assert class_response.status_code == 201, class_response.text
        battle_mage = class_response.json()

        for class_level in (1, 8):
            slots_response = await client.put(
                f"/classes/{battle_mage['id']}/spell-slots",
                params={"class_level": class_level},
                json={"slots": [{"spell_level": "CANTRIP", "slots": 2}, {"spell_level": "LEVEL_1", "slots": 2}]},
                headers=gm_headers,
            )
            assert slots_response.status_code == 200, slots_response.text

        feat_choice_response = await client.post("/feats", json={"name": "Slasher"}, headers=gm_headers)
        resilient_response = await client.post(
            "/feats",
            json={"name": "Resilient", "ability_score_increases": [{"ability": "CON", "amount": 1}]},
            headers=gm_headers,
        )
        assert feat_choice_response.status_code == 201
        assert resilient_response.status_code == 201
        feat_choice = feat_choice_response.json()
        resilient = resilient_response.json()
        resilient_asi_id = resilient["ability_score_increases"][0]["id"]

        fire_bolt = await create_spell(name="Fire Bolt", school="EVOCATION", level="CANTRIP")
        light = await create_spell(name="Light", school="ILLUSION", level="CANTRIP")
        shield_spell = await create_spell(name="Shield", school="ABJURATION", level="LEVEL_1")

        subclass_response = await client.post(
            "/subclasses",
            json={"name": "War Magic", "class_id": battle_mage["id"]},
            headers=gm_headers,
        )
        assert subclass_response.status_code == 201
        war_magic = subclass_response.json()

        create_response = await client.post(
            "/characters",
            json={
                "name": "Aria",
                "class_id": battle_mage["id"],
                "race_id": race.id,
                "strength": 16,
                "dexterity": 12,
                "constitution": 14,
                "intelligence": 10,
                "wisdom": 10,
                "charisma": 10,
                "skill_ids": [skill.id],
            },
            headers=player_headers,
        )
        assert create_response.status_code == 201, create_response.text
        character = create_response.json()
        character_id = character["id"]

        # POST /characters seeds the GM-set level-up cap at the starting
        # level; raise it so this scenario can level up to 8 freely.
        cap_response = await client.patch(
            f"/characters/{character_id}/gm-panel/max-level",
            json={"max_level": 20},
            headers=gm_headers,
        )
        assert cap_response.status_code == 200, cap_response.text

        assert character["level"] == 1
        assert character["max_hp"] == 12
        assert character["subclass_id"] is None
        assert character["subrace_id"] is None
        assert character["background_id"] is None
        assert character["ability_scores"]["strength_total"] == 16
        assert character["ability_scores"]["constitution_total"] == 14
        assert {item["ability"] for item in character["saving_throw_proficiencies"]} == {"STR", "CON"}
        assert [item["skill_id"] for item in character["skill_proficiencies"]] == [skill.id]
        assert all(item["is_expertise"] is False for item in character["skill_proficiencies"])

        for spell in (fire_bolt, light, shield_spell):
            learn_response = await client.post(
                f"/characters/{character_id}/spells",
                json={"spell_id": spell.id},
                headers=player_headers,
            )
            assert learn_response.status_code == 201, learn_response.text

        extra_cantrip = await create_spell(name="Mage Hand", school="CONJURATION", level="CANTRIP")
        blocked_response = await client.post(
            f"/characters/{character_id}/spells",
            json={"spell_id": extra_cantrip.id},
            headers=player_headers,
        )
        assert blocked_response.status_code == 400

        async def level_up(payload=None):
            return await client.post(
                f"/characters/{character_id}/progression/level-up",
                json=payload or {},
                headers=player_headers,
            )

        second = await level_up()
        third = await level_up()
        assert second.status_code == 200
        assert second.json()["max_hp"] == 20
        assert third.status_code == 200
        assert third.json()["max_hp"] == 28

        fourth = await level_up({"hit_points_gained": 1, "choice": {"type": "FEAT", "feat_id": feat_choice["id"]}})
        assert fourth.status_code == 200, fourth.text
        assert fourth.json()["level"] == 4
        assert fourth.json()["max_hp"] == 29

        zero_gain = await level_up({"hit_points_gained": 0})
        assert zero_gain.status_code == 422
        fifth = await level_up()
        assert fifth.status_code == 200
        assert fifth.json()["max_hp"] == 37
        sixth = await level_up()
        assert sixth.json()["max_hp"] == 45
        seventh = await level_up()
        assert seventh.json()["max_hp"] == 53

        eighth = await level_up(
            {
                "hit_points_gained": 8,
                "choice": {
                    "type": "ASI",
                    "increases": [{"ability": "STR", "amount": 1}, {"ability": "CON", "amount": 1}],
                },
            }
        )
        assert eighth.status_code == 200, eighth.text
        assert eighth.json()["level"] == 8
        assert eighth.json()["max_hp"] == 61

        feats_response = await client.get(
            f"/characters/{character_id}/feats", headers=player_headers
        )
        assert feats_response.status_code == 200
        assert sorted(entry["feat"]["name"] for entry in feats_response.json()) == ["Slasher"]

        choices_response = await client.get(
            f"/characters/{character_id}/progression/asi-choices", headers=player_headers
        )
        assert choices_response.status_code == 200
        choices = choices_response.json()
        feat_choices = [choice for choice in choices if choice["choice_type"] == "FEAT"]
        assert sorted((choice["class_level"] or 0) for choice in feat_choices) == [4]
        level_four_choice = next(choice for choice in feat_choices if choice["class_level"] == 4)
        assert level_four_choice["feat_id"] == feat_choice["id"]
        asi_choice = [choice for choice in choices if choice["choice_type"] == "ASI"]
        assert len(asi_choice) == 1
        assert asi_choice[0]["class_level"] == 8
        assert {item["ability"]: item["amount"] for item in asi_choice[0]["increases"]} == {"STR": 1, "CON": 1}

        subclass_patch = await client.patch(
            f"/characters/{character_id}/progression/subclass",
            json={"subclass_id": war_magic["id"]},
            headers=player_headers,
        )
        assert subclass_patch.status_code == 200
        assert subclass_patch.json()["subclass_id"] == war_magic["id"]

        subrace_patch = await client.patch(
            f"/characters/{character_id}/progression/subrace",
            json={"subrace_id": subrace.id},
            headers=player_headers,
        )
        assert subrace_patch.status_code == 200
        assert subrace_patch.json()["subrace_id"] == subrace.id

        background_patch = await client.patch(
            f"/characters/{character_id}/progression/background",
            json={"background_id": background.id},
            headers=player_headers,
        )
        assert background_patch.status_code == 200
        assert background_patch.json()["background_id"] == background.id

        second_background = await client.patch(
            f"/characters/{character_id}/progression/background",
            json={"background_id": background.id},
            headers=player_headers,
        )
        assert second_background.status_code == 409

        grant_response = await client.post(
            f"/characters/{character_id}/gm-panel/feats",
            json={"feat_id": resilient["id"], "ability_score_increase_id": resilient_asi_id},
            headers=gm_headers,
        )
        assert grant_response.status_code == 201, grant_response.text
        assert grant_response.json()["feat"]["name"] == "Resilient"

        str_boost = await client.post(
            f"/characters/{character_id}/gm-panel/asi",
            json={"increases": [{"ability": "STR", "amount": 3}]},
            headers=gm_headers,
        )
        wis_drop = await client.post(
            f"/characters/{character_id}/gm-panel/asi",
            json={"increases": [{"ability": "WIS", "amount": -1}]},
            headers=gm_headers,
        )
        assert str_boost.status_code == 201
        assert wis_drop.status_code == 201

        # The GM panel is its own ceiling: it takes STR beyond 20 up to 30.
        over_cap = await client.post(
            f"/characters/{character_id}/gm-panel/asi",
            json={"increases": [{"ability": "STR", "amount": 10}]},
            headers=gm_headers,
        )
        assert over_cap.status_code == 201  # 20 + 10 = 30

        over_thirty = await client.post(
            f"/characters/{character_id}/gm-panel/asi",
            json={"increases": [{"ability": "STR", "amount": 1}]},
            headers=gm_headers,
        )
        assert over_thirty.status_code == 400  # 31 > 30

        equip_sword = await client.post(
            f"/characters/{character_id}/gm-panel/items",
            json={"item_id": longsword.id, "quantity": 1, "is_equipped": True},
            headers=gm_headers,
        )
        add_potions = await client.post(
            f"/characters/{character_id}/gm-panel/items",
            json={"item_id": potion.id, "quantity": 5},
            headers=gm_headers,
        )
        assert equip_sword.status_code == 201
        assert equip_sword.json()["is_equipped"] is True
        assert add_potions.status_code == 201
        assert add_potions.json()["quantity"] == 5

        expertise_on = await client.patch(
            f"/characters/{character_id}/gm-panel/skills",
            params={"skill_id": skill.id},
            json={"is_expertise": True},
            headers=gm_headers,
        )
        assert expertise_on.status_code == 200
        assert expertise_on.json() == {"skill_id": skill.id, "is_expertise": True}

        final_response = await client.get(f"/characters/{character_id}", headers=player_headers)
        assert final_response.status_code == 200
        final = final_response.json()

        assert final["level"] == 8
        assert final["max_hp"] == 61
        assert final["subclass_id"] == war_magic["id"]
        assert final["subrace_id"] == subrace.id
        assert final["background_id"] == background.id

        scores = final["ability_scores"]
        assert scores["strength_total"] == 30
        assert scores["dexterity_total"] == 12
        assert scores["constitution_total"] == 16
        assert scores["intelligence_total"] == 10
        assert scores["wisdom_total"] == 9
        assert scores["charisma_total"] == 10

        proficiencies = {item["skill_id"]: item for item in final["skill_proficiencies"]}
        assert proficiencies[skill.id]["is_expertise"] is True

        stats_response = await client.get(
            f"/characters/{character_id}/gm-panel/stats", headers=gm_headers
        )
        assert stats_response.status_code == 200
        stats = stats_response.json()
        assert stats["strength"] == {"base": 16, "total": 30}
        assert stats["wisdom"] == {"base": 10, "total": 9}

        spells_response = await client.get(
            f"/characters/{character_id}/spells", headers=player_headers
        )
        assert spells_response.status_code == 200
        spell_body = spells_response.json()
        assert {slot["spell_level"]: slot["total"] for slot in spell_body["spell_slots"]} == {
            "CANTRIP": 2,
            "LEVEL_1": 2,
        }
        assert sorted(entry["spell"]["name"] for entry in spell_body["spells"]) == ["Fire Bolt", "Light", "Shield"]

        items_response = await client.get(
            f"/characters/{character_id}/items", headers=gm_headers
        )
        assert items_response.status_code == 200
        stacks = {entry["item_id"]: entry for entry in items_response.json()}
        assert stacks[longsword.id]["is_equipped"] is True
        assert stacks[potion.id]["quantity"] == 5
