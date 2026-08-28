"""Tests for character spell-slot totals and known-spell endpoints."""

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
class TestCharacterSpellSlots:
    async def test_get_spells_includes_slot_totals_for_caster(
        self, client, player, player_token, create_caster_class, create_api_character
    ):
        character_class = await create_caster_class(name="Wizard")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        response = await client.get(
            f"/characters/{character['id']}/spells",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        slots = {item["spell_level"]: item for item in body["spell_slots"]}
        assert slots["LEVEL_1"]["total"] == 2
        assert "used" not in slots["LEVEL_1"]
        assert body["spells"] == []

    async def test_non_caster_has_zero_total_slots(
        self, client, player, player_token, create_class, create_api_character
    ):
        character_class = await create_class(name="Fighter")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        response = await client.get(
            f"/characters/{character['id']}/spells",
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        slots = {item["spell_level"]: item for item in response.json()["spell_slots"]}
        assert slots.get("LEVEL_1", {"total": 0})["total"] == 0

    async def test_spell_slot_endpoints_are_removed(
        self, client, player, player_token, create_caster_class, create_api_character
    ):
        """Slot spending is gone — the old /spell-slots routes no longer exist."""
        character_class = await create_caster_class(name="Wizard")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        get_response = await client.get(
            "/characters/spell-slots",
            params={"character_id": character["id"]},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        patch_response = await client.patch(
            "/characters/spell-slots",
            params={"character_id": character["id"]},
            json={"level": "LEVEL_1", "used": 1},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert get_response.status_code == 404
        assert patch_response.status_code == 404


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
        """A level's slot total doubles as the cap on known spells of that level."""
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

    async def test_add_spell_restricted_to_matching_subclass_is_allowed(
        self,
        client,
        player,
        player_token,
        gm_token,
        create_caster_class,
        create_api_character,
        create_spell,
        create_subclass,
    ):
        character_class = await create_caster_class(name="Wizard")
        subclass = await create_subclass(class_id=character_class.id, name="Evoker")
        character, _ = await create_api_character(class_id=character_class.id, owner=player, subclass_id=subclass.id)
        spell = await create_spell(name="School Special", school="EVOCATION", level="LEVEL_1")

        restrict_response = await client.put(
            f"/spells/{spell.id}/subclasses",
            json={"subclass_ids": [subclass.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert restrict_response.status_code == 200

        response = await client.post(
            f"/characters/{character['id']}/spells",
            json={"spell_id": spell.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 201

    async def test_add_spell_restricted_to_other_subclass_returns_400(
        self,
        client,
        player,
        player_token,
        gm_token,
        create_caster_class,
        create_api_character,
        create_spell,
        create_subclass,
    ):
        character_class = await create_caster_class(name="Wizard")
        other_subclass = await create_subclass(class_id=character_class.id, name="Abjurer")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        spell = await create_spell(name="Abjurer Only", school="ABJURATION", level="LEVEL_1")

        restrict_response = await client.put(
            f"/spells/{spell.id}/subclasses",
            json={"subclass_ids": [other_subclass.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert restrict_response.status_code == 200

        response = await client.post(
            f"/characters/{character['id']}/spells",
            json={"spell_id": spell.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_add_spell_restricted_to_subrace_without_one_returns_400(
        self,
        client,
        player,
        player_token,
        create_caster_class,
        create_api_character,
        create_spell,
        create_race,
        create_subrace,
        gm_token,
    ):
        character_class = await create_caster_class(name="Wizard")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        spell = await create_spell(name="Elven Grace", school="ILLUSION", level="LEVEL_1")

        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")
        restrict_response = await client.put(
            f"/spells/{spell.id}/subraces",
            json={"subrace_ids": [subrace.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert restrict_response.status_code == 200

        response = await client.post(
            f"/characters/{character['id']}/spells",
            json={"spell_id": spell.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 400

    async def test_add_spell_restricted_to_matching_subrace_is_allowed(
        self,
        client,
        player,
        player_token,
        create_caster_class,
        create_api_character,
        create_spell,
        create_race,
        create_subrace,
        gm_token,
    ):
        character_class = await create_caster_class(name="Wizard")
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")
        character, _ = await create_api_character(
            class_id=character_class.id, owner=player, race_id=race.id, subrace_id=subrace.id
        )
        spell = await create_spell(name="Elven Grace", school="ILLUSION", level="LEVEL_1")

        restrict_response = await client.put(
            f"/spells/{spell.id}/subraces",
            json={"subrace_ids": [subrace.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert restrict_response.status_code == 200

        response = await client.post(
            f"/characters/{character['id']}/spells",
            json={"spell_id": spell.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 201

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
        body = list_response.json()
        assert [item["spell_id"] for item in body["spells"]] == [spell.id]
        assert len(body["spell_slots"]) > 0

        remove_response = await client.delete(
            f"/characters/{character['id']}/spells",
            params={"spell_id": spell.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert remove_response.status_code == 204

        after_response = await client.get(
            f"/characters/{character['id']}/spells",
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert after_response.status_code == 200
        assert after_response.json()["spells"] == []
