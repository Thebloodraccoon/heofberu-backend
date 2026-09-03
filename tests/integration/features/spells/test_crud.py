"""Tests for the spell write endpoints."""

import pytest

SPELL_PAYLOAD = {
    "name": "Magic Missile",
    "school": "EVOCATION",
    "level": "LEVEL_1",
    "cast_time": "ACTION",
    "range_type": "RANGED",
    "range_value": 120,
    "components": ["VERBAL", "SOMATIC"],
    "is_material_consumed": False,
    "duration": "INSTANTANEOUS",
    "description": "You create three glowing darts of magical force.",
}


@pytest.mark.integration
@pytest.mark.asyncio
class TestSpellCrud:
    async def test_player_cannot_create_spell(self, client, player_token):
        response = await client.post(
            "/spells",
            json=SPELL_PAYLOAD,
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 403

    async def test_gm_can_create_spell(self, client, gm_token):
        response = await client.post("/spells", json=SPELL_PAYLOAD, headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 201
        assert response.json()["name"] == "Magic Missile"
        assert response.json()["level"] == "LEVEL_1"

    async def test_create_duplicate_spell_name_returns_400(self, client, gm_token, create_spell):
        await create_spell(name="Magic Missile")
        response = await client.post("/spells", json=SPELL_PAYLOAD, headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 400

    async def test_gm_can_update_spell(self, client, gm_token, create_spell):
        spell = await create_spell(name="Old Spell Name")

        response = await client.patch(
            f"/spells/{spell.id}", json={"name": "New Spell Name"}, headers={"Authorization": f"Bearer {gm_token}"}
        )

        assert response.status_code == 200
        assert response.json()["name"] == "New Spell Name"

    async def test_gm_can_set_available_classes_and_races(
        self, client, gm_token, create_spell, create_class, create_race
    ):
        spell = await create_spell(name="Restricted Spell")
        character_class = await create_class(name="Sorcerer", hit_dice="D6", spellcasting_ability="CHA")
        race = await create_race(name="High Elf")

        classes_response = await client.put(
            f"/spells/{spell.id}/classes",
            json={"class_ids": [character_class.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert classes_response.status_code == 200
        assert [item["id"] for item in classes_response.json()["available_classes"]] == [character_class.id]

        races_response = await client.put(
            f"/spells/{spell.id}/races",
            json={"race_ids": [race.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert races_response.status_code == 200
        assert [item["id"] for item in races_response.json()["available_races"]] == [race.id]

    async def test_gm_can_set_available_subclasses_and_subraces(
        self, client, gm_token, create_spell, create_class, create_race, create_subclass, create_subrace
    ):
        spell = await create_spell(name="Restricted Spell")
        character_class = await create_class(name="Sorcerer", hit_dice="D6", spellcasting_ability="CHA")
        subclass = await create_subclass(class_id=character_class.id, name="Wild Magic")
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")

        subclasses_response = await client.put(
            f"/spells/{spell.id}/subclasses",
            json={"subclass_ids": [subclass.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert subclasses_response.status_code == 200
        body = subclasses_response.json()
        assert [item["id"] for item in body["available_subclasses"]] == [subclass.id]
        # Other dimensions untouched.
        assert body["available_classes"] == []
        assert body["available_races"] == []

        subraces_response = await client.put(
            f"/spells/{spell.id}/subraces",
            json={"subrace_ids": [subrace.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert subraces_response.status_code == 200
        body = subraces_response.json()
        assert [item["id"] for item in body["available_subraces"]] == [subrace.id]
        assert [item["id"] for item in body["available_subclasses"]] == [subclass.id]

    async def test_set_availability_replaces_previous_list(self, client, gm_token, create_spell, create_race):
        """Full-replace semantics: a new list drops the previous entries."""
        spell = await create_spell(name="Replaceable Spell")
        first_race = await create_race(name="Elf")
        second_race = await create_race(name="Dwarf")

        await client.put(
            f"/spells/{spell.id}/races",
            json={"race_ids": [first_race.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        response = await client.put(
            f"/spells/{spell.id}/subraces",
            json={"subrace_ids": []},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert response.status_code == 200

        replace_response = await client.put(
            f"/spells/{spell.id}/races",
            json={"race_ids": [second_race.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert replace_response.status_code == 200
        assert [item["id"] for item in replace_response.json()["available_races"]] == [second_race.id]

    async def test_unknown_subclass_or_subrace_id_returns_400(self, client, gm_token, create_spell):
        spell = await create_spell(name="Picky Spell")

        subclasses_response = await client.put(
            f"/spells/{spell.id}/subclasses",
            json={"subclass_ids": [999999]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert subclasses_response.status_code == 400

        subraces_response = await client.put(
            f"/spells/{spell.id}/subraces",
            json={"subrace_ids": [999999]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert subraces_response.status_code == 400

    async def test_player_cannot_set_availability(self, client, player_token, create_spell):
        spell = await create_spell(name="Locked Spell")

        subclasses_response = await client.put(
            f"/spells/{spell.id}/subclasses",
            json={"subclass_ids": []},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert subclasses_response.status_code == 403

        subraces_response = await client.put(
            f"/spells/{spell.id}/subraces",
            json={"subrace_ids": []},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert subraces_response.status_code == 403

    async def test_gm_cannot_delete_spell(self, client, gm_token, create_spell):
        spell = await create_spell(name="Doomed Spell")

        response = await client.delete(f"/spells/{spell.id}", headers={"Authorization": f"Bearer {gm_token}"})

        assert response.status_code == 403
        assert (await client.get(f"/spells/{spell.id}")).status_code == 200

    async def test_founder_can_delete_spell(self, client, founder_token, create_spell):
        spell = await create_spell(name="Doomed Spell")

        response = await client.delete(f"/spells/{spell.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 204
        assert (await client.get(f"/spells/{spell.id}")).status_code == 404

    async def test_delete_spell_known_by_character_returns_409(
        self, client, founder_token, db_session, create_spell, create_class, create_user, create_character
    ):
        from app.models.character_spell_model import CharacterSpell

        spell = await create_spell(name="Cure Wounds")
        player = await create_user()
        char_class = await create_class(name="Druid")
        character = await create_character(owner_id=player.id, class_id=char_class.id)

        db_session.add(CharacterSpell(character_id=character.id, spell_id=spell.id))
        await db_session.commit()

        response = await client.delete(f"/spells/{spell.id}", headers={"Authorization": f"Bearer {founder_token}"})

        assert response.status_code == 409
        assert (await client.get(f"/spells/{spell.id}")).status_code == 200
