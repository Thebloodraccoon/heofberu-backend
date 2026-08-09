"""Tests for character spell-slot and known-spell endpoints."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterSpellSlots:
    async def test_get_spell_slots_for_caster(
        self, client, player, player_token, create_caster_class, create_api_character
    ):
        character_class = await create_caster_class(name="Wizard")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        response = await client.get(
            f"/characters/{character['id']}/spell-slots",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        slots = {item["spell_level"]: item for item in response.json()}
        assert slots["LEVEL_1"]["total"] == 2

    async def test_spend_spell_slot(self, client, player, player_token, create_caster_class, create_api_character):
        character_class = await create_caster_class(name="Wizard")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        response = await client.patch(
            f"/characters/{character['id']}/spell-slots",
            json={"level": "LEVEL_1", "used": 2},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        assert response.json()["used"] == 2

    async def test_over_spend_spell_slot_returns_400(
        self, client, player, player_token, create_caster_class, create_api_character
    ):
        character_class = await create_caster_class(name="Wizard")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        response = await client.patch(
            f"/characters/{character['id']}/spell-slots",
            json={"level": "LEVEL_1", "used": 3},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_invalid_spell_level_returns_422(
        self, client, player, player_token, create_caster_class, create_api_character
    ):
        character_class = await create_caster_class(name="Wizard")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        response = await client.patch(
            f"/characters/{character['id']}/spell-slots",
            json={"level": "LEVEL_10", "used": 1},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 422

    async def test_cannot_set_total_via_schema(
        self, client, player, player_token, create_caster_class, create_api_character
    ):
        """`total` is not client-settable — sending it is rejected with a 422."""
        character_class = await create_caster_class(name="Wizard")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        response = await client.patch(
            f"/characters/{character['id']}/spell-slots",
            json={"level": "LEVEL_1", "used": 0, "total": 4},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 422

    async def test_cannot_spend_into_level_without_slots(
        self, client, player, player_token, create_class, create_character
    ):
        """A class with no spell-slot progression grants no slots — spending is rejected."""
        character_class = await create_class(name="Fighter")
        character = await create_character(owner_id=player.id, class_id=character_class.id)

        response = await client.patch(
            f"/characters/{character.id}/spell-slots",
            json={"level": "LEVEL_1", "used": 1},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterKnownSpells:
    async def test_add_known_spell(
        self, client, player, player_token, create_caster_class, create_api_character, create_spell
    ):
        character_class = await create_caster_class(name="Wizard")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        spell = await create_spell(name="Magic Missile", school="EVOCATION", level="LEVEL_1")

        response = await client.post(
            f"/characters/{character['id']}/spells",
            json={"spell_id": spell.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 201
        assert response.json()["spell_id"] == spell.id

    async def test_add_duplicate_spell_returns_409(
        self, client, player, player_token, create_caster_class, create_api_character, create_spell
    ):
        character_class = await create_caster_class(name="Wizard")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        spell = await create_spell(name="Magic Missile", school="EVOCATION", level="LEVEL_1")

        await client.post(
            f"/characters/{character['id']}/spells",
            json={"spell_id": spell.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        response = await client.post(
            f"/characters/{character['id']}/spells",
            json={"spell_id": spell.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 409

    async def test_add_spell_with_no_slot_available_returns_400(
        self, client, player, player_token, create_caster_class, create_api_character, create_spell
    ):
        character_class = await create_caster_class(name="Wizard", slots=[{"spell_level": "LEVEL_1", "slots": 0}])
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        spell = await create_spell(name="Magic Missile", school="EVOCATION", level="LEVEL_1")

        response = await client.post(
            f"/characters/{character['id']}/spells",
            json={"spell_id": spell.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_add_spell_not_available_to_character_class_returns_400(
        self,
        client,
        player,
        player_token,
        create_caster_class,
        create_api_character,
        create_spell,
        create_class,
        gm_token,
    ):
        character_class = await create_caster_class(name="Wizard")
        other_class = await create_class(name="Fighter", hit_dice="D10")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        spell = await create_spell(name="Divine Word", school="EVOCATION", level="LEVEL_1")

        restriction_response = await client.put(
            f"/spells/{spell.id}/classes",
            json={"class_ids": [other_class.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert restriction_response.status_code == 200

        response = await client.post(
            f"/characters/{character['id']}/spells",
            json={"spell_id": spell.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_list_and_remove_known_spell(
        self, client, player, player_token, create_caster_class, create_api_character, create_spell
    ):
        character_class = await create_caster_class(name="Wizard")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        spell = await create_spell(name="Magic Missile", school="EVOCATION", level="LEVEL_1")

        await client.post(
            f"/characters/{character['id']}/spells",
            json={"spell_id": spell.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        list_response = await client.get(
            f"/characters/{character['id']}/spells",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert list_response.status_code == 200
        assert [item["spell_id"] for item in list_response.json()] == [spell.id]

        remove_response = await client.delete(
            f"/characters/{character['id']}/spells/{spell.id}",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert remove_response.status_code == 204

        after_response = await client.get(
            f"/characters/{character['id']}/spells",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert after_response.json() == []
