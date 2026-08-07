"""Tests for character progression endpoints: race/class change and leveling up."""

import pytest


def set_class_spell_slots(client, gm_token, character_class, class_level, slots):
    """Set a class's spell slot progression for a level via the API (GM only)."""
    response = client.put(
        f"/classes/{character_class.id}/spell-slots/{class_level}",
        json={"slots": slots},
        headers={"Authorization": f"Bearer {gm_token}"},
    )
    assert response.status_code == 200, response.text
    return character_class


def set_race_ability_bonuses(client, gm_token, race, bonuses):
    """Replace a race's ability bonuses via the API (GM only)."""
    response = client.put(
        f"/races/{race.id}/ability-bonuses",
        json={"ability_bonuses": bonuses},
        headers={"Authorization": f"Bearer {gm_token}"},
    )
    assert response.status_code == 200, response.text
    return race


@pytest.mark.integration
class TestRaceChange:
    def test_owner_can_change_race_and_ability_scores_are_recomputed(
        self, client, player, player_token, gm_token, create_class, create_race, create_api_character
    ):
        character_class = create_class(name="Fighter")
        character, _ = create_api_character(class_id=character_class.id, owner=player, dexterity=10)
        race = set_race_ability_bonuses(client, gm_token, create_race(name="Elf"), [{"ability": "DEX", "bonus": 2}])

        response = client.patch(
            f"/characters/{character['id']}/progression/race",
            json={"race_id": race.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["race_id"] == race.id
        assert body["ability_scores"]["dexterity_total"] == 12

    def test_clearing_race_drops_its_bonuses(
        self, client, player, player_token, gm_token, create_class, create_race, create_api_character
    ):
        character_class = create_class(name="Fighter")
        race = set_race_ability_bonuses(client, gm_token, create_race(name="Elf"), [{"ability": "DEX", "bonus": 2}])
        character, _ = create_api_character(class_id=character_class.id, owner=player, race_id=race.id, dexterity=10)

        response = client.patch(
            f"/characters/{character['id']}/progression/race",
            json={"race_id": None},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["race_id"] is None
        assert body["ability_scores"]["dexterity_total"] == 10

    def test_unknown_race_returns_404(self, client, player, player_token, create_class, create_api_character):
        character_class = create_class(name="Fighter")
        character, _ = create_api_character(class_id=character_class.id, owner=player)

        response = client.patch(
            f"/characters/{character['id']}/progression/race",
            json={"race_id": 999999},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 404

    def test_player_cannot_change_other_players_character_race(
        self, client, player_token, create_user, create_class, create_character, create_race
    ):
        character_class = create_class(name="Fighter")
        other = create_user(username="other", email="other@example.com")
        character = create_character(owner_id=other.id, class_id=character_class.id)
        race = create_race(name="Elf")

        response = client.patch(
            f"/characters/{character.id}/progression/race",
            json={"race_id": race.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403


@pytest.mark.integration
class TestClassChange:
    def test_owner_can_change_class_and_spell_slots_are_reapplied(
        self, client, player, player_token, create_caster_class, create_class, create_api_character
    ):
        character_class = create_class(name="Fighter")
        caster_class = create_caster_class(name="Wizard")
        character, _ = create_api_character(class_id=character_class.id, owner=player)

        response = client.patch(
            f"/characters/{character['id']}/progression/class",
            json={"class_id": caster_class.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["class_id"] == caster_class.id
        slots = {item["spell_level"]: item for item in body["spell_slots"]}
        assert slots["LEVEL_1"]["total"] == 2

    def test_unknown_class_returns_404(self, client, player, player_token, create_class, create_api_character):
        character_class = create_class(name="Fighter")
        character, _ = create_api_character(class_id=character_class.id, owner=player)

        response = client.patch(
            f"/characters/{character['id']}/progression/class",
            json={"class_id": 999999},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 404

    def test_player_cannot_change_other_players_character_class(
        self, client, player_token, create_user, create_class, create_character
    ):
        character_class = create_class(name="Fighter")
        other = create_user(username="other", email="other@example.com")
        character = create_character(owner_id=other.id, class_id=character_class.id)
        new_class = create_class(name="Wizard", hit_dice="D6", spellcasting_ability="INT")

        response = client.patch(
            f"/characters/{character.id}/progression/class",
            json={"class_id": new_class.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403


@pytest.mark.integration
class TestLevelUp:
    def test_non_asi_level_up_applies_default_hp_gain(
        self, client, player, player_token, create_class, create_api_character
    ):
        character_class = create_class(name="Fighter", hit_dice="D10")
        character, _ = create_api_character(class_id=character_class.id, owner=player, level=1, max_hp=10)

        response = client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["level"] == 2
        assert body["max_hp"] == 16

    def test_level_up_with_custom_hp_gain(self, client, player, player_token, create_class, create_api_character):
        character_class = create_class(name="Fighter", hit_dice="D10")
        character, _ = create_api_character(class_id=character_class.id, owner=player, level=1, max_hp=10)

        response = client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={"hit_points_gained": 8},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["max_hp"] == 18

    def test_hp_gain_outside_hit_die_range_returns_400(
        self, client, player, player_token, create_class, create_api_character
    ):
        character_class = create_class(name="Fighter", hit_dice="D10")
        character, _ = create_api_character(class_id=character_class.id, owner=player, level=1)

        response = client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={"hit_points_gained": 11},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    def test_choice_at_non_asi_level_returns_400(
        self, client, player, player_token, create_class, create_api_character
    ):
        character_class = create_class(name="Fighter", hit_dice="D10")
        character, _ = create_api_character(class_id=character_class.id, owner=player, level=1)

        response = client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={"choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 1}]}},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    def test_asi_level_requires_a_choice(self, client, player, player_token, create_class, create_api_character):
        character_class = create_class(name="Fighter", hit_dice="D10")
        character, _ = create_api_character(class_id=character_class.id, owner=player, level=3)

        response = client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    def test_asi_level_up_applies_increases_and_records_choice(
        self, client, player, player_token, create_class, create_api_character
    ):
        character_class = create_class(name="Fighter", hit_dice="D10")
        character, _ = create_api_character(class_id=character_class.id, owner=player, level=3, strength=14)

        response = client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={"choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 2}]}},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["level"] == 4
        assert body["ability_scores"]["strength_total"] == 16

        choices_response = client.get(
            f"/characters/{character['id']}/progression/asi-choices",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert choices_response.status_code == 200
        choices = choices_response.json()
        assert len(choices) == 1
        assert choices[0]["class_level"] == 4
        assert choices[0]["choice_type"] == "ASI"
        assert choices[0]["increases"] == [{"ability": "STR", "amount": 2}]

    def test_asi_above_score_cap_returns_400(self, client, player, player_token, create_class, create_character):
        character_class = create_class(name="Fighter", hit_dice="D10")
        character = create_character(owner_id=player.id, class_id=character_class.id, level=3, strength=19)

        response = client.post(
            f"/characters/{character.id}/progression/level-up",
            json={"choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 2}]}},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    def test_feat_choice_grants_feat_and_records_choice(
        self, client, player, player_token, create_class, create_api_character, create_feat
    ):
        character_class = create_class(name="Fighter", hit_dice="D10")
        character, _ = create_api_character(class_id=character_class.id, owner=player, level=3)
        feat = create_feat(name="Alert")

        response = client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={"choice": {"type": "FEAT", "feat_id": feat.id}},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["level"] == 4

        feats_response = client.get(
            f"/characters/{character['id']}/feats",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert [item["feat_id"] for item in feats_response.json()] == [feat.id]

        choices_response = client.get(
            f"/characters/{character['id']}/progression/asi-choices",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        choices = choices_response.json()
        assert choices[0]["choice_type"] == "FEAT"
        assert choices[0]["feat_id"] == feat.id

    def test_feat_choice_with_unknown_feat_returns_404(
        self, client, player, player_token, create_class, create_api_character
    ):
        character_class = create_class(name="Fighter", hit_dice="D10")
        character, _ = create_api_character(class_id=character_class.id, owner=player, level=3)

        response = client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={"choice": {"type": "FEAT", "feat_id": 999999}},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 404

    def test_feat_choice_already_known_returns_409(
        self, client, player, player_token, create_class, create_api_character, create_feat
    ):
        character_class = create_class(name="Fighter", hit_dice="D10")
        character, _ = create_api_character(class_id=character_class.id, owner=player, level=3)
        feat = create_feat(name="Alert")

        grant_response = client.post(
            f"/characters/{character['id']}/feats",
            json={"feat_id": feat.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert grant_response.status_code == 201

        response = client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={"choice": {"type": "FEAT", "feat_id": feat.id}},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 409

    def test_feat_choice_with_asi_increase_applies_bonus(
        self,
        client,
        player,
        player_token,
        gm_token,
        create_class,
        create_api_character,
        create_feat,
    ):
        character_class = create_class(name="Fighter", hit_dice="D10")
        character, _ = create_api_character(class_id=character_class.id, owner=player, level=3, strength=13)
        feat = create_feat(name="Resilient")
        asi_response = client.put(
            f"/feats/{feat.id}/ability-score-increases",
            json={"ability_score_increases": [{"ability": "STR", "amount": 1}]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert asi_response.status_code == 200
        asi_id = asi_response.json()["ability_score_increases"][0]["id"]

        response = client.post(
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

    def test_level_up_reapplies_spell_slot_progression(
        self, client, player, player_token, gm_token, create_caster_class, create_api_character
    ):
        character_class = create_caster_class(name="Wizard")
        set_class_spell_slots(
            client,
            gm_token,
            character_class,
            2,
            [{"spell_level": "LEVEL_1", "slots": 3}],
        )
        character, _ = create_api_character(class_id=character_class.id, owner=player, level=1)

        response = client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        slots = {item["spell_level"]: item for item in response.json()["spell_slots"]}
        assert slots["LEVEL_1"]["total"] == 3

    def test_level_up_at_max_level_returns_400(self, client, player, player_token, create_class, create_api_character):
        character_class = create_class(name="Fighter", hit_dice="D10")
        character, _ = create_api_character(class_id=character_class.id, owner=player, level=20)

        response = client.post(
            f"/characters/{character['id']}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    def test_player_cannot_level_up_other_players_character(
        self, client, player_token, create_user, create_class, create_character
    ):
        character_class = create_class(name="Fighter", hit_dice="D10")
        other = create_user(username="other", email="other@example.com")
        character = create_character(owner_id=other.id, class_id=character_class.id)

        response = client.post(
            f"/characters/{character.id}/progression/level-up",
            json={},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403


@pytest.mark.integration
class TestASIChoices:
    def test_list_asi_choices_is_empty_for_new_character(
        self, client, player, player_token, create_class, create_api_character
    ):
        character_class = create_class(name="Fighter", hit_dice="D10")
        character, _ = create_api_character(class_id=character_class.id, owner=player)

        response = client.get(
            f"/characters/{character['id']}/progression/asi-choices",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json() == []

    def test_asi_choices_accumulate_across_levels(
        self, client, player, player_token, create_class, create_api_character, create_feat
    ):
        character_class = create_class(name="Fighter", hit_dice="D10")
        character, _ = create_api_character(class_id=character_class.id, owner=player, level=3)
        feat = create_feat(name="Alert")

        for class_level in range(4, 9):
            if class_level == 8:
                payload = {"choice": {"type": "FEAT", "feat_id": feat.id}}
            elif class_level == 4:
                payload = {"choice": {"type": "ASI", "increases": [{"ability": "STR", "amount": 1}]}}
            else:
                payload = {}
            response = client.post(
                f"/characters/{character['id']}/progression/level-up",
                json=payload,
                headers={"Authorization": f"Bearer {player_token}"},
            )
            assert response.status_code == 200, response.text

        response = client.get(
            f"/characters/{character['id']}/progression/asi-choices",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        choices = response.json()
        assert [choice["class_level"] for choice in choices] == [4, 8]
        assert [choice["choice_type"] for choice in choices] == ["ASI", "FEAT"]

    def test_player_cannot_view_other_players_asi_choices(
        self, client, player_token, create_user, create_class, create_character
    ):
        character_class = create_class(name="Fighter", hit_dice="D10")
        other = create_user(username="other", email="other@example.com")
        character = create_character(owner_id=other.id, class_id=character_class.id)

        response = client.get(
            f"/characters/{character.id}/progression/asi-choices",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403
