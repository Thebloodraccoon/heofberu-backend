"""
End-to-end spell flows for characters: per-level known-spell caps (including
the CANTRIP row), ANDed availability dimensions, the GET /characters/spells
payload shape, and the absence of any client-writable slot path.
"""

import pytest


async def add_spell(client, character_id, spell_id, token):
    return await client.post(
        "/characters/spells",
        params={"character_id": character_id},
        json={"spell_id": spell_id},
        headers={"Authorization": f"Bearer {token}"},
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestSpellsPayloadShape:
    async def test_get_spells_returns_exact_envelope(
        self, client, player, player_token, create_caster_class, create_api_character
    ):
        character_class = await create_caster_class(name="Wizard", slots=[{"spell_level": "CANTRIP", "slots": 2}])
        character, _ = await create_api_character(class_id=character_class.id, owner=player)

        response = await client.get(
            "/characters/spells",
            params={"character_id": character["id"]},
            headers={"Authorization": f"Bearer {player_token}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"spell_slots", "spells"}
        assert body["spells"] == []
        assert len(body["spell_slots"]) == 1
        assert set(body["spell_slots"][0]) == {"spell_level", "total"}
        assert body["spell_slots"][0] == {"spell_level": "CANTRIP", "total": 2}

    async def test_known_spell_entries_embed_the_spell_payload(
        self, client, player, player_token, create_caster_class, create_api_character, create_spell
    ):
        character_class = await create_caster_class(name="Wizard")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        spell = await create_spell(name="Magic Missile", school="EVOCATION", level="LEVEL_1")

        add_response = await add_spell(client, character["id"], spell.id, player_token)
        assert add_response.status_code == 201

        list_response = await client.get(
            "/characters/spells",
            params={"character_id": character["id"]},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        body = list_response.json()
        assert [entry["spell_id"] for entry in body["spells"]] == [spell.id]
        assert body["spells"][0]["spell"]["name"] == "Magic Missile"
        assert {slot["spell_level"]: slot["total"] for slot in body["spell_slots"]} == {"LEVEL_1": 2}


@pytest.mark.integration
@pytest.mark.asyncio
class TestPerLevelKnownSpellCaps:
    async def test_cantrip_cap_is_enforced_via_cantrip_slot_row(
        self, client, player, player_token, create_caster_class, create_api_character, create_spell
    ):
        """A CANTRIP progression row caps known cantrips exactly like a leveled row."""
        character_class = await create_caster_class(
            name="Cantrip Wizard",
            slots=[{"spell_level": "CANTRIP", "slots": 1}, {"spell_level": "LEVEL_1", "slots": 2}],
        )
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        first = await create_spell(name="Fire Bolt", school="EVOCATION", level="CANTRIP")
        second = await create_spell(name="Prestidigitation", school="TRANSMUTATION", level="CANTRIP")

        ok = await add_spell(client, character["id"], first.id, player_token)
        assert ok.status_code == 201

        blocked = await add_spell(client, character["id"], second.id, player_token)
        assert blocked.status_code == 400

    async def test_learn_spells_up_to_cap_then_rejected_then_swap(
        self, client, player, player_token, create_caster_class, create_api_character, create_spell
    ):
        character_class = await create_caster_class(name="Wizard", slots=[{"spell_level": "LEVEL_1", "slots": 2}])
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        missile = await create_spell(name="Magic Missile", school="EVOCATION", level="LEVEL_1")
        charm = await create_spell(name="Charm Person", school="ENCHANTMENT", level="LEVEL_1")
        shield = await create_spell(name="Shield", school="ABJURATION", level="LEVEL_1")

        first = await add_spell(client, character["id"], missile.id, player_token)
        second = await add_spell(client, character["id"], charm.id, player_token)
        assert first.status_code == 201
        assert second.status_code == 201

        over_cap = await add_spell(client, character["id"], shield.id, player_token)
        assert over_cap.status_code == 400

        remove_response = await client.delete(
            "/characters/spells",
            params={"character_id": character["id"], "spell_id": missile.id},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert remove_response.status_code == 204

        swap = await add_spell(client, character["id"], shield.id, player_token)
        assert swap.status_code == 201

        list_response = await client.get(
            "/characters/spells",
            params={"character_id": character["id"]},
            headers={"Authorization": f"Bearer {player_token}"},
        )
        assert sorted(entry["spell_id"] for entry in list_response.json()["spells"]) == [charm.id, shield.id]

    async def test_missing_slot_row_means_zero_capacity(
        self, client, player, player_token, create_caster_class, create_api_character, create_spell
    ):
        """A level with no progression row at all allows no known spells of that level."""
        character_class = await create_caster_class(name="Cantrip Only", slots=[{"spell_level": "CANTRIP", "slots": 2}])
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        spell = await create_spell(name="Sleep", school="ENCHANTMENT", level="LEVEL_1")

        response = await add_spell(client, character["id"], spell.id, player_token)

        assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
class TestAvailabilityDimensionsAreAnded:
    async def test_matching_every_restricted_dimension_allows_the_spell(
        self,
        client,
        player,
        player_token,
        gm_token,
        create_caster_class,
        create_api_character,
        create_spell,
        create_race,
        create_subrace,
    ):
        character_class = await create_caster_class(name="Wizard")
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")
        character, _ = await create_api_character(
            class_id=character_class.id, owner=player, race_id=race.id, subrace_id=subrace.id
        )
        spell = await create_spell(name="Elven Missile", school="EVOCATION", level="LEVEL_1")

        class_response = await client.put(
            "/spells/classes",
            params={"spell_id": spell.id},
            json={"class_ids": [character_class.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        subrace_response = await client.put(
            "/spells/subraces",
            params={"spell_id": spell.id},
            json={"subrace_ids": [subrace.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert class_response.status_code == 200
        assert subrace_response.status_code == 200

        response = await add_spell(client, character["id"], spell.id, player_token)
        assert response.status_code == 201

    async def test_failing_any_single_dimension_blocks_the_spell(
        self,
        client,
        player,
        player_token,
        gm_token,
        create_caster_class,
        create_api_character,
        create_spell,
        create_race,
        create_subrace,
    ):
        """Class matches and subrace is unrestricted — but the race dimension excludes."""
        character_class = await create_caster_class(name="Wizard")
        own_race = await create_race(name="Human")
        other_race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=own_race.id, name="Stock Human")
        character, _ = await create_api_character(
            class_id=character_class.id, owner=player, race_id=own_race.id, subrace_id=subrace.id
        )
        spell = await create_spell(name="Elven Grace", school="ILLUSION", level="LEVEL_1")

        class_response = await client.put(
            "/spells/classes",
            params={"spell_id": spell.id},
            json={"class_ids": [character_class.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        race_response = await client.put(
            "/spells/races",
            params={"spell_id": spell.id},
            json={"race_ids": [other_race.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert class_response.status_code == 200
        assert race_response.status_code == 200

        response = await add_spell(client, character["id"], spell.id, player_token)
        assert response.status_code == 400

    async def test_empty_dimension_is_unrestricted_while_others_still_apply(
        self,
        client,
        player,
        player_token,
        gm_token,
        create_caster_class,
        create_api_character,
        create_spell,
        create_class,
    ):
        """Subclass/race/subraces lists are empty (unrestricted); the class restriction alone decides."""
        character_class = await create_caster_class(name="Wizard")
        other_class = await create_class(name="Fighter")
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        spell = await create_spell(name="Divine Word", school="EVOCATION", level="LEVEL_1")

        restrict_response = await client.put(
            "/spells/classes",
            params={"spell_id": spell.id},
            json={"class_ids": [other_class.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert restrict_response.status_code == 200

        response = await add_spell(client, character["id"], spell.id, player_token)
        assert response.status_code == 400

    async def test_subclass_restriction_blocks_character_without_subclass(
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
        character, _ = await create_api_character(class_id=character_class.id, owner=player)
        spell = await create_spell(name="School Special", school="EVOCATION", level="LEVEL_1")

        restrict_response = await client.put(
            "/spells/subclasses",
            params={"spell_id": spell.id},
            json={"subclass_ids": [subclass.id]},
            headers={"Authorization": f"Bearer {gm_token}"},
        )
        assert restrict_response.status_code == 200

        response = await add_spell(client, character["id"], spell.id, player_token)
        assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
class TestSlotsAreNeverClientWritable:
    async def test_legacy_slot_spend_routes_do_not_exist(self, client, player_token):
        responses = [
            await client.get(
                "/characters/spell-slots",
                params={"character_id": 1},
                headers={"Authorization": f"Bearer {player_token}"},
            ),
            await client.post(
                "/characters/spell-slots",
                params={"character_id": 1},
                json={"spell_level": "LEVEL_1", "used": 1},
                headers={"Authorization": f"Bearer {player_token}"},
            ),
            await client.put(
                "/characters/spell-slots",
                params={"character_id": 1},
                json={"spell_level": "LEVEL_1", "total": 9},
                headers={"Authorization": f"Bearer {player_token}"},
            ),
            await client.patch(
                "/characters/spell-slots",
                params={"character_id": 1},
                json={"level": "LEVEL_1", "used": 1},
                headers={"Authorization": f"Bearer {player_token}"},
            ),
            await client.delete(
                "/characters/spell-slots",
                params={"character_id": 1},
                headers={"Authorization": f"Bearer {player_token}"},
            ),
        ]

        assert all(response.status_code == 404 for response in responses)
