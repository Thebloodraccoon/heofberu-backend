"""
End-to-end source ability-bonus reconciliation: a GM edits a race's or
subrace's ability bonuses after characters of that source already exist,
and those characters' ``character_ability_scores`` cache rows refresh in the
same transaction.

``GET /characters/{id}`` embeds ``ability_scores`` straight from that cache
(never recomputed on read), so it is the right oracle here — the GM-panel
stats overview always computes fresh and would mask a stale cache.
"""

import pytest


async def get_ability_total(client, character_id, token, field):
    """Effective total read from the cache-backed character detail (as-is, never recomputed)."""

    response = await client.get(
        f"/characters/{character_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()["ability_scores"][field]


async def set_race_bonuses(client, gm_token, race_id, bonuses):
    response = await client.put(
        f"/races/{race_id}/ability-bonuses",
        json={"ability_bonuses": bonuses},
        headers={"Authorization": f"Bearer {gm_token}"},
    )
    assert response.status_code == 200, response.text


async def set_subrace_bonuses(client, gm_token, subrace_id, bonuses):
    response = await client.put(
        f"/subraces/{subrace_id}/ability-bonuses",
        json={"ability_bonuses": bonuses},
        headers={"Authorization": f"Bearer {gm_token}"},
    )
    assert response.status_code == 200, response.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestRaceAbilityBonusRefresh:
    async def test_race_bonus_edit_refreshes_existing_characters_stats_and_cache(
        self, client, player, gm_token, create_class, create_api_character, create_race, db_session
    ):
        from sqlalchemy import select

        from app.models import CharacterAbilityScore

        character_class = await create_class(name="Fighter")
        race = await create_race(name="Dragonborn")
        await set_race_bonuses(client, gm_token, race.id, [{"ability": "STR", "bonus": 2}])

        character, token = await create_api_character(
            class_id=character_class.id, owner=player, race_id=race.id, strength=10
        )
        assert await get_ability_total(client, character["id"], token, "strength_total") == 12

        await set_race_bonuses(client, gm_token, race.id, [{"ability": "STR", "bonus": 1}])

        # The detail read is served from the cache — a stale row would say 12.
        assert await get_ability_total(client, character["id"], token, "strength_total") == 11

        cached = (
            await db_session.execute(
                select(CharacterAbilityScore).where(CharacterAbilityScore.character_id == character["id"])
            )
        ).scalar_one()
        assert cached.strength_total == 11

    async def test_race_bonus_edit_does_not_touch_other_races_characters(
        self, client, player, gm_token, create_class, create_api_character, create_race
    ):
        character_class = await create_class(name="Fighter")
        race_a = await create_race(name="Dragonborn")
        race_b = await create_race(name="Elf")
        await set_race_bonuses(client, gm_token, race_a.id, [{"ability": "STR", "bonus": 2}])

        char_a, token_a = await create_api_character(
            class_id=character_class.id, owner=player, race_id=race_a.id, strength=10
        )
        char_b, token_b = await create_api_character(
            class_id=character_class.id, owner=player, race_id=race_b.id, strength=10
        )
        assert await get_ability_total(client, char_a["id"], token_a, "strength_total") == 12
        assert await get_ability_total(client, char_b["id"], token_b, "strength_total") == 10

        await set_race_bonuses(client, gm_token, race_a.id, [{"ability": "STR", "bonus": 1}])

        assert await get_ability_total(client, char_a["id"], token_a, "strength_total") == 11
        assert await get_ability_total(client, char_b["id"], token_b, "strength_total") == 10


@pytest.mark.integration
@pytest.mark.asyncio
class TestSubraceAbilityBonusRefresh:
    async def test_subrace_bonus_edit_refreshes_existing_characters_stats(
        self, client, player, gm_token, create_class, create_api_character, create_race, create_subrace
    ):
        character_class = await create_class(name="Fighter")
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")
        await set_subrace_bonuses(client, gm_token, subrace.id, [{"ability": "DEX", "bonus": 2}])

        character, token = await create_api_character(
            class_id=character_class.id, owner=player, race_id=race.id, subrace_id=subrace.id, dexterity=10
        )
        assert await get_ability_total(client, character["id"], token, "dexterity_total") == 12

        await set_subrace_bonuses(client, gm_token, subrace.id, [{"ability": "DEX", "bonus": 1}])

        assert await get_ability_total(client, character["id"], token, "dexterity_total") == 11


@pytest.mark.integration
@pytest.mark.asyncio
class TestRaceAndSubraceStacking:
    async def test_editing_either_source_updates_the_stacked_total(
        self, client, player, gm_token, create_class, create_api_character, create_race, create_subrace
    ):
        character_class = await create_class(name="Fighter")
        race = await create_race(name="Elf")
        subrace = await create_subrace(race_id=race.id, name="High Elf")
        await set_race_bonuses(client, gm_token, race.id, [{"ability": "STR", "bonus": 1}])
        await set_subrace_bonuses(client, gm_token, subrace.id, [{"ability": "STR", "bonus": 1}])

        character, token = await create_api_character(
            class_id=character_class.id, owner=player, race_id=race.id, subrace_id=subrace.id, strength=10
        )
        assert await get_ability_total(client, character["id"], token, "strength_total") == 12

        await set_race_bonuses(client, gm_token, race.id, [{"ability": "STR", "bonus": 2}])
        assert await get_ability_total(client, character["id"], token, "strength_total") == 13

        # Clearing the subrace's bonuses leaves only the race's +2.
        await set_subrace_bonuses(client, gm_token, subrace.id, [])
        assert await get_ability_total(client, character["id"], token, "strength_total") == 12
