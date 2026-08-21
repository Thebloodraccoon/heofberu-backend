"""Tests for character crud endpoints: CRUD, HP, and resting."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterCreate:
    async def test_any_authenticated_user_can_create_character(
        self, client, player_token, create_class, create_background
    ):
        character_class = await create_class(name="Fighter", hit_dice="D10")
        background = await create_background()

        response = await client.post(
            "/characters",
            json={"name": "Aragorn", "level": 1, "class_id": character_class.id, "background_id": background.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Aragorn"
        assert body["class_id"] == character_class.id
        assert body["level"] == 1

    async def test_create_character_requires_class(self, client, player_token):
        response = await client.post(
            "/characters",
            json={"name": "Aragorn", "level": 1},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 422

    async def test_create_character_requires_auth(self, client, create_class):
        character_class = await create_class(name="Fighter")

        response = await client.post(
            "/characters",
            json={"name": "Nobody", "class_id": character_class.id},
        )

        assert response.status_code == 401

    async def test_create_character_with_unknown_class_returns_404(self, client, player_token, create_background):
        background = await create_background()

        response = await client.post(
            "/characters",
            json={"name": "Ghost", "class_id": 999999, "background_id": background.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 404

    async def test_create_caster_character_applies_spell_slots(
        self, client, player_token, create_caster_class, create_background
    ):
        character_class = await create_caster_class(name="Wizard")
        background = await create_background()

        response = await client.post(
            "/characters",
            json={
                "name": "Gandalf",
                "level": 1,
                "class_id": character_class.id,
                "background_id": background.id,
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 201
        character_id = response.json()["id"]
        slots_response = await client.get(
            f"/characters/{character_id}/spell-slots",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        slots = {item["spell_level"]: item for item in slots_response.json()}
        assert slots["LEVEL_1"]["total"] == 2
        assert slots["LEVEL_1"]["used"] == 0

    async def test_create_character_with_subclass(
        self, client, player_token, create_class, create_subclass, create_background
    ):
        character_class = await create_class(name="Fighter")
        subclass = await create_subclass(class_id=character_class.id, name="Champion")
        background = await create_background()

        response = await client.post(
            "/characters",
            json={
                "name": "Aragorn",
                "level": 1,
                "class_id": character_class.id,
                "subclass_id": subclass.id,
                "background_id": background.id,
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 201
        assert response.json()["subclass_id"] == subclass.id

    async def test_create_character_with_subclass_of_another_class_returns_404(
        self, client, player_token, create_class, create_subclass, create_background
    ):
        fighter = await create_class(name="Fighter")
        wizard = await create_class(name="Wizard", hit_dice="D6", spellcasting_ability="INT")
        wizard_subclass = await create_subclass(class_id=wizard.id, name="School of Evocation")
        background = await create_background()

        response = await client.post(
            "/characters",
            json={
                "name": "Ghost",
                "class_id": fighter.id,
                "subclass_id": wizard_subclass.id,
                "background_id": background.id,
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterRead:
    async def test_player_list_only_returns_own_characters(
        self, client, player, player_token, create_user, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        other = await create_user(username="other", email="other@example.com")
        await create_character(owner_id=player.id, class_id=character_class.id, name="Mine")
        await create_character(owner_id=other.id, class_id=character_class.id, name="Theirs")

        response = await client.get("/characters", headers={"Authorization": f"Bearer {player_token}"})

        assert response.status_code == 200
        names = [item["name"] for item in response.json()["items"]]
        assert names == ["Mine"]

    async def test_gm_sees_all_characters(self, client, gm_token, create_user, create_class, create_character):
        character_class = await create_class(name="Fighter")
        player1 = await create_user()
        player2 = await create_user(username="other", email="other@example.com")
        await create_character(owner_id=player1.id, class_id=character_class.id, name="Mine")
        await create_character(owner_id=player2.id, class_id=character_class.id, name="Theirs")

        response = await client.get("/characters", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 200
        assert len(response.json()["items"]) == 2

    async def test_list_filters_by_search_on_name(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        await create_character(owner_id=player.id, class_id=character_class.id, name="Aragorn")
        await create_character(owner_id=player.id, class_id=character_class.id, name="Legolas")

        response = await client.get(
            "/characters?search=ara",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert [item["name"] for item in response.json()["items"]] == ["Aragorn"]

    async def test_list_filters_by_class_id(self, client, player, player_token, create_class, create_character):
        fighter = await create_class(name="Fighter")
        wizard = await create_class(name="Wizard", hit_dice="D6", spellcasting_ability="INT")
        await create_character(owner_id=player.id, class_id=fighter.id, name="Conan")
        await create_character(owner_id=player.id, class_id=wizard.id, name="Gandalf")

        response = await client.get(
            f"/characters?class_id={wizard.id}",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert [item["name"] for item in response.json()["items"]] == ["Gandalf"]

    async def test_list_search_combines_with_class_filter(
        self, client, player, player_token, create_class, create_character
    ):
        fighter = await create_class(name="Fighter")
        wizard = await create_class(name="Wizard", hit_dice="D6", spellcasting_ability="INT")
        await create_character(owner_id=player.id, class_id=fighter.id, name="Gandalf")
        await create_character(owner_id=player.id, class_id=wizard.id, name="Gandalf the Grey")

        response = await client.get(
            f"/characters?search=gandalf&class_id={wizard.id}",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert [item["name"] for item in response.json()["items"]] == ["Gandalf the Grey"]

    async def test_get_character_by_id(self, client, player, player_token, create_class, create_api_character):
        character_class = await create_class(name="Fighter")
        character, _ = await create_api_character(class_id=character_class.id, owner=player, name="Boromir")

        response = await client.get(
            f"/characters/{character['id']}", headers={"Authorization": f"Bearer {player_token}"}
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Boromir"
        assert response.json()["ability_scores"]["strength_total"] == 10

    async def test_player_cannot_get_other_players_character(
        self, client, player_token, create_user, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        other = await create_user(username="other", email="other@example.com")
        character = await create_character(owner_id=other.id, class_id=character_class.id)

        response = await client.get(f"/characters/{character.id}", headers={"Authorization": f"Bearer {player_token}"})

        assert response.status_code == 403

    async def test_gm_can_get_any_character(self, client, gm_token, create_user, create_class, create_character):
        character_class = await create_class(name="Fighter")
        other = await create_user(username="other", email="other@example.com")
        character = await create_character(owner_id=other.id, class_id=character_class.id)

        response = await client.get(f"/characters/{character.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 200

    async def test_get_character_404(self, client, player_token):
        assert (
            await client.get("/characters/999999", headers={"Authorization": f"Bearer {player_token}"})
        ).status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterUpdate:
    async def test_owner_can_update_character(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id, name="Old Name")

        response = await client.patch(
            f"/characters/{character.id}",
            json={"name": "New Name"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

    async def test_player_cannot_update_other_players_character(
        self, client, player_token, create_user, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        other = await create_user(username="other", email="other@example.com")
        character = await create_character(owner_id=other.id, class_id=character_class.id)

        response = await client.patch(
            f"/characters/{character.id}",
            json={"name": "Hacked"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_subclass_is_not_editable_via_plain_patch(
        self, client, player, player_token, create_class, create_character
    ):
        """Subclass changes go through the progression endpoint, not a plain PATCH."""
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.patch(
            f"/characters/{character.id}",
            json={"subclass_id": 999999, "subclass": "Arcane Archer"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["subclass_id"] is None

    async def test_strength_is_not_editable_via_patch(
        self, client, player, player_token, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id, strength=10)

        response = await client.patch(
            f"/characters/{character.id}",
            json={"strength": 12},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert "strength" not in response.json()

    async def test_class_id_is_not_editable(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        other_class = await create_class(name="Wizard", hit_dice="D6", spellcasting_ability="INT")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.patch(
            f"/characters/{character.id}",
            json={"class_id": other_class.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["class_id"] == character_class.id


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterDelete:
    async def test_owner_can_delete_character(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.delete(
            f"/characters/{character.id}", headers={"Authorization": f"Bearer {player_token}"}
        )

        assert response.status_code == 204
        assert (
            await client.get(f"/characters/{character.id}", headers={"Authorization": f"Bearer {player_token}"})
        ).status_code == 404

    async def test_player_cannot_delete_other_players_character(
        self, client, player_token, create_user, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        other = await create_user(username="other", email="other@example.com")
        character = await create_character(owner_id=other.id, class_id=character_class.id)

        response = await client.delete(
            f"/characters/{character.id}", headers={"Authorization": f"Bearer {player_token}"}
        )

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterHp:
    async def test_apply_damage_via_delta(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id, max_hp=20, current_hp=20)

        response = await client.patch(
            f"/characters/{character.id}/hp",
            json={"delta": -5},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["current_hp"] == 15

    async def test_heal_via_delta_clamps_to_max(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id, max_hp=20, current_hp=10)

        response = await client.patch(
            f"/characters/{character.id}/hp",
            json={"delta": 50},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["current_hp"] == 20

    async def test_set_absolute_hp(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id, max_hp=20, current_hp=20)

        response = await client.patch(
            f"/characters/{character.id}/hp",
            json={"current_hp": 8},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["current_hp"] == 8

    async def test_delta_and_absolute_together_returns_400(
        self, client, player, player_token, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.patch(
            f"/characters/{character.id}/hp",
            json={"delta": -5, "current_hp": 10},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_damage_is_absorbed_by_temp_hp_first(
        self, client, player, player_token, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(
            owner_id=player.id, class_id=character_class.id, max_hp=20, current_hp=20, temp_hp=8
        )

        response = await client.patch(
            f"/characters/{character.id}/hp",
            json={"delta": -5},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["current_hp"] == 20
        assert response.json()["temp_hp"] == 3

    async def test_damage_overflow_past_temp_hits_current(
        self, client, player, player_token, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(
            owner_id=player.id, class_id=character_class.id, max_hp=20, current_hp=20, temp_hp=3
        )

        response = await client.patch(
            f"/characters/{character.id}/hp",
            json={"delta": -7},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["current_hp"] == 16
        assert response.json()["temp_hp"] == 0

    async def test_healing_does_not_restore_temp_hp(
        self, client, player, player_token, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(
            owner_id=player.id, class_id=character_class.id, max_hp=20, current_hp=10, temp_hp=5
        )

        response = await client.patch(
            f"/characters/{character.id}/hp",
            json={"delta": 4},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["current_hp"] == 14
        assert response.json()["temp_hp"] == 5

    async def test_temp_hp_gain_replaces_only_when_higher(
        self, client, player, player_token, create_class, create_character
    ):
        character_class = await create_class(name="Fighter")
        character = await create_character(
            owner_id=player.id, class_id=character_class.id, max_hp=20, current_hp=15, temp_hp=6
        )

        lower = await client.patch(
            f"/characters/{character.id}/hp",
            json={"temp_hp": 4},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert lower.status_code == 200
        assert lower.json()["temp_hp"] == 6

        higher = await client.patch(
            f"/characters/{character.id}/hp",
            json={"temp_hp": 9},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert higher.status_code == 200
        assert higher.json()["temp_hp"] == 9


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterRest:
    async def test_long_rest_restores_hp_and_slots(
        self, client, player, player_token, create_caster_class, create_background
    ):
        character_class = await create_caster_class(name="Wizard")
        background = await create_background()
        character_response = await client.post(
            "/characters",
            json={
                "name": "Gandalf",
                "level": 1,
                "class_id": character_class.id,
                "background_id": background.id,
                "max_hp": 20,
                "current_hp": 20,
            },
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert character_response.status_code == 201
        character_id = character_response.json()["id"]

        hp_response = await client.patch(
            f"/characters/{character_id}/hp",
            json={"delta": -12},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert hp_response.status_code == 200
        assert hp_response.json()["current_hp"] == 8

        slot_response = await client.patch(
            f"/characters/{character_id}/spell-slots",
            json={"level": "LEVEL_1", "used": 2},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert slot_response.status_code == 200

        rest_response = await client.post(
            f"/characters/{character_id}/rest",
            json={"type": "long"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert rest_response.status_code == 200
        body = rest_response.json()
        assert body["current_hp"] == 20
        slots_response = await client.get(
            f"/characters/{character_id}/spell-slots",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        slots = {item["spell_level"]: item for item in slots_response.json()}
        assert slots["LEVEL_1"]["used"] == 0

    async def test_short_rest_is_accepted(self, client, player, player_token, create_class, create_background):
        character_class = await create_class(name="Fighter")
        background = await create_background()
        response = await client.post(
            "/characters",
            json={"name": "Conan", "class_id": character_class.id, "background_id": background.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert response.status_code == 201
        character_id = response.json()["id"]

        rest_response = await client.post(
            f"/characters/{character_id}/rest",
            json={"type": "short"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert rest_response.status_code == 200

    async def test_invalid_rest_type_returns_422(self, client, player, player_token, create_class, create_character):
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.post(
            f"/characters/{character.id}/rest",
            json={"type": "overnight"},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 422
