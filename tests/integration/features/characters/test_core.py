"""Tests for character core endpoints: CRUD, HP, and resting."""

import pytest


@pytest.mark.integration
class TestCharacterCreate:
    def test_any_authenticated_user_can_create_character(self, client, player_token, create_class):
        character_class = create_class(name="Fighter", hit_dice="D10")

        response = client.post(
            "/characters/",
            json={"name": "Aragorn", "level": 1, "class_id": character_class.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Aragorn"
        assert body["class_id"] == character_class.id
        assert body["level"] == 1

    def test_create_character_requires_auth(self, client, create_class):
        character_class = create_class(name="Fighter")

        response = client.post(
            "/characters/",
            json={"name": "Nobody", "class_id": character_class.id},
        )

        assert response.status_code == 401

    def test_create_character_with_unknown_class_returns_404(self, client, player_token):
        response = client.post(
            "/characters/",
            json={"name": "Ghost", "class_id": 999999},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 404

    def test_create_caster_character_applies_spell_slots(self, client, player_token, create_caster_class):
        character_class = create_caster_class(name="Wizard")

        response = client.post(
            "/characters/",
            json={"name": "Gandalf", "level": 1, "class_id": character_class.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 201
        slots = {item["spell_level"]: item for item in response.json()["spell_slots"]}
        assert slots["LEVEL_1"]["total"] == 2
        assert slots["LEVEL_1"]["used"] == 0


@pytest.mark.integration
class TestCharacterRead:
    def test_player_list_only_returns_own_characters(
        self, client, player, player_token, create_user, create_class, create_character
    ):
        character_class = create_class(name="Fighter")
        other = create_user(username="other", email="other@example.com")
        create_character(owner_id=player.id, class_id=character_class.id, name="Mine")
        create_character(owner_id=other.id, class_id=character_class.id, name="Theirs")

        response = client.get("/characters/", headers={"Authorization": f"Bearer {player_token}"})

        assert response.status_code == 200
        names = [item["name"] for item in response.json()]
        assert names == ["Mine"]

    def test_gm_sees_all_characters(self, client, gm_token, create_user, create_class, create_character):
        character_class = create_class(name="Fighter")
        player1 = create_user()
        player2 = create_user(username="other", email="other@example.com")
        create_character(owner_id=player1.id, class_id=character_class.id, name="Mine")
        create_character(owner_id=player2.id, class_id=character_class.id, name="Theirs")

        response = client.get("/characters/", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_filters_by_search_on_name(self, client, player, player_token, create_class, create_character):
        character_class = create_class(name="Fighter")
        create_character(owner_id=player.id, class_id=character_class.id, name="Aragorn")
        create_character(owner_id=player.id, class_id=character_class.id, name="Legolas")

        response = client.get(
            "/characters/?search=ara",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert [item["name"] for item in response.json()] == ["Aragorn"]

    def test_list_filters_by_class_id(self, client, player, player_token, create_class, create_character):
        fighter = create_class(name="Fighter")
        wizard = create_class(name="Wizard", hit_dice="D6", spellcasting_ability="INT")
        create_character(owner_id=player.id, class_id=fighter.id, name="Conan")
        create_character(owner_id=player.id, class_id=wizard.id, name="Gandalf")

        response = client.get(
            f"/characters/?class_id={wizard.id}",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert [item["name"] for item in response.json()] == ["Gandalf"]

    def test_list_search_combines_with_class_filter(self, client, player, player_token, create_class, create_character):
        fighter = create_class(name="Fighter")
        wizard = create_class(name="Wizard", hit_dice="D6", spellcasting_ability="INT")
        create_character(owner_id=player.id, class_id=fighter.id, name="Gandalf")
        create_character(owner_id=player.id, class_id=wizard.id, name="Gandalf the Grey")

        response = client.get(
            f"/characters/?search=gandalf&class_id={wizard.id}",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert [item["name"] for item in response.json()] == ["Gandalf the Grey"]

    def test_get_character_by_id(self, client, player, player_token, create_class, create_character):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id, name="Boromir")

        response = client.get(f"/characters/{character.id}", headers={"Authorization": f"Bearer {player_token}"})

        assert response.status_code == 200
        assert response.json()["name"] == "Boromir"
        assert response.json()["ability_scores"]["strength_total"] == 10

    def test_player_cannot_get_other_players_character(
        self, client, player_token, create_user, create_class, create_character
    ):
        character_class = create_class(name="Fighter")
        other = create_user(username="other", email="other@example.com")
        character = create_character(owner_id=other.id, class_id=character_class.id)

        response = client.get(f"/characters/{character.id}", headers={"Authorization": f"Bearer {player_token}"})

        assert response.status_code == 403

    def test_gm_can_get_any_character(self, client, gm_token, create_user, create_class, create_character):
        character_class = create_class(name="Fighter")
        other = create_user(username="other", email="other@example.com")
        character = create_character(owner_id=other.id, class_id=character_class.id)

        response = client.get(f"/characters/{character.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 200

    def test_get_character_404(self, client, player_token):
        assert client.get("/characters/999999", headers={"Authorization": f"Bearer {player_token}"}).status_code == 404


@pytest.mark.integration
class TestCharacterUpdate:
    def test_owner_can_update_character(self, client, player, player_token, create_class, create_character):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id, name="Old Name")

        response = client.patch(
            f"/characters/{character.id}",
            json={"name": "New Name"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

    def test_player_cannot_update_other_players_character(
        self, client, player_token, create_user, create_class, create_character
    ):
        character_class = create_class(name="Fighter")
        other = create_user(username="other", email="other@example.com")
        character = create_character(owner_id=other.id, class_id=character_class.id)

        response = client.patch(
            f"/characters/{character.id}",
            json={"name": "Hacked"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    def test_owner_can_update_subclass(self, client, player, player_token, create_class, create_character):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)

        response = client.patch(
            f"/characters/{character.id}",
            json={"subclass": "Arcane Archer"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["subclass"] == "Arcane Archer"

    def test_update_strength_refreshes_ability_scores(
        self, client, player, player_token, create_class, create_character
    ):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id, strength=10)

        response = client.patch(
            f"/characters/{character.id}",
            json={"strength": 12},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["ability_scores"]["strength_total"] == 12

    def test_class_id_is_not_editable(self, client, player, player_token, create_class, create_character):
        character_class = create_class(name="Fighter")
        other_class = create_class(name="Wizard", hit_dice="D6", spellcasting_ability="INT")
        character = create_character(owner_id=player.id, class_id=character_class.id)

        response = client.patch(
            f"/characters/{character.id}",
            json={"class_id": other_class.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["class_id"] == character_class.id


@pytest.mark.integration
class TestCharacterDelete:
    def test_owner_can_delete_character(self, client, player, player_token, create_class, create_character):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)

        response = client.delete(f"/characters/{character.id}", headers={"Authorization": f"Bearer {player_token}"})

        assert response.status_code == 204
        assert (
            client.get(f"/characters/{character.id}", headers={"Authorization": f"Bearer {player_token}"}).status_code
            == 404
        )

    def test_player_cannot_delete_other_players_character(
        self, client, player_token, create_user, create_class, create_character
    ):
        character_class = create_class(name="Fighter")
        other = create_user(username="other", email="other@example.com")
        character = create_character(owner_id=other.id, class_id=character_class.id)

        response = client.delete(f"/characters/{character.id}", headers={"Authorization": f"Bearer {player_token}"})

        assert response.status_code == 403


@pytest.mark.integration
class TestCharacterHp:
    def test_apply_damage_via_delta(self, client, player, player_token, create_class, create_character):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id, max_hp=20, current_hp=20)

        response = client.patch(
            f"/characters/{character.id}/hp",
            json={"delta": -5},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["current_hp"] == 15

    def test_heal_via_delta_clamps_to_max(self, client, player, player_token, create_class, create_character):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id, max_hp=20, current_hp=10)

        response = client.patch(
            f"/characters/{character.id}/hp",
            json={"delta": 50},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["current_hp"] == 20

    def test_set_absolute_hp(self, client, player, player_token, create_class, create_character):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id, max_hp=20, current_hp=20)

        response = client.patch(
            f"/characters/{character.id}/hp",
            json={"current_hp": 8},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["current_hp"] == 8

    def test_delta_and_absolute_together_returns_400(
        self, client, player, player_token, create_class, create_character
    ):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)

        response = client.patch(
            f"/characters/{character.id}/hp",
            json={"delta": -5, "current_hp": 10},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400


@pytest.mark.integration
class TestCharacterRest:
    def test_long_rest_restores_hp_and_slots(self, client, player, player_token, create_caster_class):
        character_class = create_caster_class(name="Wizard")
        character_response = client.post(
            "/characters/",
            json={"name": "Gandalf", "level": 1, "class_id": character_class.id, "max_hp": 20, "current_hp": 20},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert character_response.status_code == 201
        character_id = character_response.json()["id"]

        hp_response = client.patch(
            f"/characters/{character_id}/hp",
            json={"delta": -12},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert hp_response.status_code == 200
        assert hp_response.json()["current_hp"] == 8

        slot_response = client.patch(
            f"/characters/{character_id}/spell-slots",
            json={"level": "LEVEL_1", "used": 2},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert slot_response.status_code == 200

        rest_response = client.post(
            f"/characters/{character_id}/rest",
            json={"type": "long"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert rest_response.status_code == 200
        body = rest_response.json()
        assert body["current_hp"] == 20
        slots = {item["spell_level"]: item for item in body["spell_slots"]}
        assert slots["LEVEL_1"]["used"] == 0

    def test_short_rest_is_accepted(self, client, player, player_token, create_class):
        character_class = create_class(name="Fighter")
        response = client.post(
            "/characters/",
            json={"name": "Conan", "class_id": character_class.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert response.status_code == 201
        character_id = response.json()["id"]

        rest_response = client.post(
            f"/characters/{character_id}/rest",
            json={"type": "short"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert rest_response.status_code == 200

    def test_invalid_rest_type_returns_422(self, client, player, player_token, create_class, create_character):
        character_class = create_class(name="Fighter")
        character = create_character(owner_id=player.id, class_id=character_class.id)

        response = client.post(
            f"/characters/{character.id}/rest",
            json={"type": "overnight"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 422
